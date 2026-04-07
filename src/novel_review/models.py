"""T02: Pydantic数据模型 — chunk manifest, phase1 light/deep, phase2, final report"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Phase0: Chunk Manifest ──────────────────────────────────────────
class ChunkInfo(BaseModel):
    chunk_id: int
    char_range: tuple[int, int]
    chapter_ref: str = ""
    text: str = Field(exclude=True, default="")  # 不序列化到JSON
    analysis_depth: str = "light"  # "light" | "deep"


class ChunkManifest(BaseModel):
    source_file: str
    source_file_sha256: str
    total_chars: int
    total_chunks: int
    chunks: list[ChunkInfo]


# ── Phase1 Light Screening ──────────────────────────────────────────
class StateChange(BaseModel):
    entity: str
    change: str


class LightResult(BaseModel):
    chunk_id: int
    char_range: tuple[int, int]
    chapter_ref: str = ""
    plot_events: list[str] = []
    characters_present: list[str] = []
    plot_progression: str = ""  # "yes: ..." or "no: ..."
    state_changes: list[StateChange] = []
    pacing_score: int = Field(ge=1, le=5, default=3)
    candidate_flags: list[str] = []


# ── Phase1 Deep Analysis ───────────────────────────────────────────
class Evidence(BaseModel):
    quote: str = Field(max_length=60)
    char_range: tuple[int, int] = (0, 0)
    chapter_ref: str = ""
    reason: str = ""


class ForeshadowingItem(BaseModel):
    description: str
    status: str = "planted"  # "planted" | "resolved"
    chunk_id: int = 0


class DeepResult(BaseModel):
    chunk_id: int
    char_range: tuple[int, int]
    chapter_ref: str = ""
    plot_events: list[str] = []
    characters_present: list[str] = []
    emotional_tone: str = ""
    worldbuilding_elements: list[str] = []
    foreshadowing: list[ForeshadowingItem] = []
    pacing_score: int = Field(ge=1, le=5, default=3)
    information_density: int = Field(ge=1, le=5, default=3)
    notable_writing: list[str] = []
    evidence: list[Evidence] = []
    defects_detected: list[str] = []


# ── Phase2 Cross-Chunk Synthesis ────────────────────────────────────
class CharacterArc(BaseModel):
    name: str
    appearances: list[int] = []  # chunk_ids
    traits: list[str] = []
    arc_summary: str = ""


class ForeshadowingPair(BaseModel):
    description: str
    planted_chunk: int
    resolved_chunk: Optional[int] = None
    status: str = "open"  # "open" | "resolved" | "broken"


class CrossChunkAnalysis(BaseModel):
    pacing_curve: list[int] = []  # pacing_score per chunk
    character_arcs: list[CharacterArc] = []
    foreshadowing_pairs: list[ForeshadowingPair] = []
    setting_conflicts: list[str] = []
    emotion_curve: list[str] = []  # emotional_tone per chunk
    coverage: dict = {}  # {"total": N, "deep": M, "ratio": float}


# ── Phase3 Final Evaluation ─────────────────────────────────────────
class TechniqueEvidence(BaseModel):
    technique: str
    quote: str = Field(max_length=60)
    chapter_ref: str = ""
    explanation: str = ""


class QualitativeAnnotation(BaseModel):
    dimension_id: str
    dimension_name: str
    style_tags: list[str] = []
    techniques: list[TechniqueEvidence] = []
    summary: str = ""


class DimensionScore(BaseModel):
    dimension_id: str
    dimension_name: str
    score: float = Field(ge=1.0, le=10.0)
    confidence: str = "high"  # "high" | "medium" | "low"
    reason: str = ""
    evidence: list[Evidence] = []


class DefectReport(BaseModel):
    rule_id: str
    rule_name: str
    location: str = ""  # chunk range or chapter
    severity: str = "medium"  # "mild" | "medium" | "severe"
    description: str = ""
    evidence: list[Evidence] = []


class PerspectiveReview(BaseModel):
    perspective: str  # "literary" | "commercial"
    strengths: list[str] = []
    weaknesses: list[str] = []
    verdict: str = ""


class FinalReport(BaseModel):
    # 基本信息
    title: str = ""
    total_chars: int = 0
    total_chunks: int = 0
    genre_guess: str = ""
    # 覆盖度
    read_mode: str = ""  # "full" | "sampled"
    deep_ratio: float = 0.0
    confidence_note: str = ""
    # 评分（仅 scorable 维度）
    dimension_scores: list[DimensionScore] = []
    qualitative_annotations: list[QualitativeAnnotation] = []
    weighted_total: float = 0.0
    recommendation_stars: int = Field(ge=1, le=5, default=3)
    one_line_summary: str = ""
    # 视角
    perspectives: list[PerspectiveReview] = []
    # 缺陷
    defects: list[DefectReport] = []
    # 曲线
    pacing_curve: list[int] = []
    # 人物
    character_arcs: list[CharacterArc] = []
    # 建议
    improvement_suggestions: list[str] = []
