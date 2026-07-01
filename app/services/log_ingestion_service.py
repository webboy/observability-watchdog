"""Request-time log ingestion orchestration."""

from __future__ import annotations

import uuid
from typing import Any, BinaryIO, Iterable

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.ingestion_run import IngestionRun
from app.repositories.app_repository import AppRepository
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.log_event_repository import LogEventRepository
from app.schemas.log_ingestion import (
    IngestionResponse,
    LogEventsRequest,
    ValidationErrorDetail,
    ValidationResponse,
    ValidationWarningDetail,
)
from app.services.dedupe_service import generate_dedupe_key
from app.services.ecs_parser import ParseFailure, ParsedLogEvent, parse_event, parse_json_line

BATCH_SIZE = 500
MAX_VALIDATION_DETAILS = 50


class AppNotFoundError(Exception):
    """Raised when the target app does not exist."""


class LogIngestionService:
    """Coordinates request-time parsing, dedupe, and persistence."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.app_repo = AppRepository()
        self.run_repo = IngestionRunRepository()
        self.log_repo = LogEventRepository()

    def _get_app_or_raise(self, app_id: uuid.UUID):
        app = self.app_repo.get_by_id(self.db, app_id)
        if app is None:
            raise AppNotFoundError(f"App '{app_id}' not found")
        return app

    def _build_row(
        self,
        *,
        app_id: uuid.UUID,
        ingestion_run_id: uuid.UUID,
        parsed: ParsedLogEvent,
    ) -> dict[str, Any]:
        return {
            "app_id": app_id,
            "ingestion_run_id": ingestion_run_id,
            "event_id": parsed.event_id,
            "dedupe_key": generate_dedupe_key(app_id, parsed),
            "timestamp": parsed.timestamp,
            "service_name": parsed.service_name,
            "log_level": parsed.log_level,
            "message": parsed.message,
            "event_dataset": parsed.event_dataset,
            "event_outcome": parsed.event_outcome,
            "event_duration_ns": parsed.event_duration_ns,
            "http_status_code": parsed.http_status_code,
            "url_path": parsed.url_path,
            "trace_id": parsed.trace_id,
            "span_id": parsed.span_id,
            "transaction_id": parsed.transaction_id,
            "error_type": parsed.error_type,
            "error_message": parsed.error_message,
            "raw_event_json": parsed.raw_event_json,
        }

    def _flush_batch(
        self,
        *,
        app_id: uuid.UUID,
        ingestion_run_id: uuid.UUID,
        batch: list[ParsedLogEvent],
    ) -> tuple[int, int]:
        rows = [
            self._build_row(app_id=app_id, ingestion_run_id=ingestion_run_id, parsed=parsed)
            for parsed in batch
        ]
        inserted = self.log_repo.insert_many_on_conflict_do_nothing(self.db, rows)
        skipped = len(batch) - inserted
        return inserted, skipped

    def _ingest_parsed_events(
        self,
        *,
        app_id: uuid.UUID,
        run: IngestionRun,
        parsed_events: Iterable[ParsedLogEvent],
        total_lines: int,
        rejected_events: int,
        filename: str | None,
    ) -> IngestionResponse:
        accepted_events = 0
        skipped_duplicates = 0
        batch: list[ParsedLogEvent] = []

        for parsed in parsed_events:
            batch.append(parsed)
            if len(batch) >= BATCH_SIZE:
                inserted, skipped = self._flush_batch(
                    app_id=app_id,
                    ingestion_run_id=run.id,
                    batch=batch,
                )
                accepted_events += inserted
                skipped_duplicates += skipped
                batch.clear()

        if batch:
            inserted, skipped = self._flush_batch(
                app_id=app_id,
                ingestion_run_id=run.id,
                batch=batch,
            )
            accepted_events += inserted
            skipped_duplicates += skipped

        status = "processing" if accepted_events > 0 else "completed"
        finalized = self.run_repo.update_request_counters(
            self.db,
            run,
            total_lines=total_lines,
            accepted_events=accepted_events,
            rejected_events=rejected_events,
            skipped_duplicates=skipped_duplicates,
            status=status,
        )

        return IngestionResponse(
            ingestion_run_id=finalized.id,
            filename=filename,
            total_lines=total_lines,
            accepted_events=accepted_events,
            rejected_events=rejected_events,
            skipped_duplicates=skipped_duplicates,
            detected_anomalies=finalized.detected_anomalies,
            alerts_triggered=finalized.alerts_triggered,
            status=finalized.status,
        )

    def ingest_events(self, app_id: uuid.UUID, payload: LogEventsRequest) -> IngestionResponse:
        """Ingest a JSON batch of ECS-compatible events."""
        self._get_app_or_raise(app_id)

        run = self.run_repo.create(
            self.db,
            app_id=app_id,
            source_type="api_batch",
            source_name="logs/events",
        )

        parsed_events: list[ParsedLogEvent] = []
        rejected_events = 0

        for index, raw_event in enumerate(payload.events):
            result = parse_event(raw_event, source_index=index)
            if isinstance(result, ParseFailure):
                rejected_events += 1
                continue
            parsed_events.append(result)

        return self._ingest_parsed_events(
            app_id=app_id,
            run=run,
            parsed_events=parsed_events,
            total_lines=len(payload.events),
            rejected_events=rejected_events,
            filename=None,
        )

    def ingest_upload(self, app_id: uuid.UUID, upload_file: UploadFile) -> IngestionResponse:
        """Ingest an uploaded ECS-compatible JSONL file line-by-line."""
        self._get_app_or_raise(app_id)

        run = self.run_repo.create(
            self.db,
            app_id=app_id,
            source_type="file_upload",
            source_name="logs/upload",
            filename=upload_file.filename,
        )

        parsed_events: list[ParsedLogEvent] = []
        rejected_events = 0
        total_lines = 0

        file_obj: BinaryIO = upload_file.file
        file_obj.seek(0)
        for line_number, line_bytes in enumerate(file_obj, start=1):
            total_lines += 1
            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                rejected_events += 1
                continue

            result = parse_json_line(line, line_number)
            if isinstance(result, ParseFailure):
                rejected_events += 1
                continue
            parsed_events.append(result)

        return self._ingest_parsed_events(
            app_id=app_id,
            run=run,
            parsed_events=parsed_events,
            total_lines=total_lines,
            rejected_events=rejected_events,
            filename=upload_file.filename,
        )

    def validate_events(self, app_id: uuid.UUID, payload: LogEventsRequest) -> ValidationResponse:
        """Validate events without creating ingestion runs or log rows."""
        self._get_app_or_raise(app_id)

        valid_events = 0
        rejected_events = 0
        errors: list[ValidationErrorDetail] = []
        warnings: list[ValidationWarningDetail] = []

        for index, raw_event in enumerate(payload.events):
            result = parse_event(raw_event, source_index=index)
            if isinstance(result, ParseFailure):
                rejected_events += 1
                if len(errors) < MAX_VALIDATION_DETAILS:
                    errors.append(ValidationErrorDetail(index=index, message=result.message))
                continue

            valid_events += 1
            for warning in result.warnings:
                if len(warnings) < MAX_VALIDATION_DETAILS:
                    warnings.append(ValidationWarningDetail(index=index, message=warning))

        return ValidationResponse(
            total_events=len(payload.events),
            valid_events=valid_events,
            rejected_events=rejected_events,
            errors=errors,
            warnings=warnings,
        )
