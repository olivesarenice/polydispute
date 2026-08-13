import os
from datetime import datetime, timezone
from typing import Optional, Union

from config import PipelineConfig


class TimeWindow:
    """
    Standardized timestamp container for pipeline orchestration windows.
    Pre-computes UTC datetime, ISO 8601 strings, and Unix epoch seconds.
    """

    def __init__(
        self,
        t0: Union[datetime, int, float, str],
        t1: Union[datetime, int, float, str],
        runtime_unix: Optional[int] = None,
        run_id: Optional[str] = None,
    ):
        self.t0_dt = self._to_utc_dt(t0)
        self.t1_dt = self._to_utc_dt(t1)

        self.iso_t0 = self.t0_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.iso_t1 = self.t1_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.unix_t0 = int(self.t0_dt.timestamp())
        self.unix_t1 = int(self.t1_dt.timestamp())

        now_utc = datetime.now(timezone.utc)
        self.runtime_unix = (
            runtime_unix if runtime_unix is not None else int(now_utc.timestamp())
        )
        self.run_id = run_id or f"run_{self.runtime_unix}"

    @property
    def t0(self) -> str:
        return self.iso_t0

    @property
    def t1(self) -> str:
        return self.iso_t1

    @staticmethod
    def _to_utc_dt(val: Union[datetime, int, float, str]) -> datetime:
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=timezone.utc)
        if isinstance(val, str):
            clean_str = val.replace("Z", "+00:00")
            if "T" not in clean_str:
                clean_str += "T00:00:00+00:00"
            return datetime.fromisoformat(clean_str)
        raise ValueError(f"Unsupported timestamp value: {val}")

    def __repr__(self) -> str:
        return f"<TimeWindow iso={self.iso_t0} -> {self.iso_t1} runtime_unix={self.runtime_unix} run_id={self.run_id}>"


def get_stage_output_path(stage_name: str, runtime_unix: int, ext: str = "json") -> str:
    """
    Constructs stage-specific output file path under pipeline/data/raw/{stage_name}/output_{runtime_unix}.{ext}.
    Creates the stage directory if it does not exist.
    """
    stage_dir = os.path.join(PipelineConfig.RAW_STAGING_DIR, stage_name)
    os.makedirs(stage_dir, exist_ok=True)
    clean_ext = ext.lstrip(".")
    return os.path.join(stage_dir, f"output_{runtime_unix}.{clean_ext}")


def get_latest_stage_file(stage_name: str) -> str:
    """
    Scans pipeline/data/raw/{stage_name}/ and returns the absolute path of the latest output_{unix}.{ext} file.
    Ranks files by the numeric unix timestamp embedded in the filename.
    Raises FileNotFoundError if no matching output files exist.
    """
    stage_dir = os.path.join(PipelineConfig.RAW_STAGING_DIR, stage_name)
    if not os.path.exists(stage_dir):
        raise FileNotFoundError(f"Stage directory does not exist: {stage_dir}")

    candidates = []
    for entry in os.listdir(stage_dir):
        if entry.startswith("output_") and os.path.isfile(
            os.path.join(stage_dir, entry)
        ):
            # Parse timestamp from output_<unix>.<ext>
            name_part = entry.split(".")[0]
            ts_str = name_part.replace("output_", "")
            if ts_str.isdigit():
                candidates.append((int(ts_str), os.path.join(stage_dir, entry)))

    if not candidates:
        raise FileNotFoundError(f"No staged output files found in {stage_dir}")

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]
