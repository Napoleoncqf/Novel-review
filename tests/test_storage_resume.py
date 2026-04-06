"""断点续传与缓存恢复回归测试"""
import sys
import json
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel_review.storage import Storage


@pytest.fixture
def tmp_storage(tmp_path):
    """创建临时Storage实例"""
    artifacts = tmp_path / "artifacts"
    with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
         patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
         patch("novel_review.storage.get_prompt_version", return_value="v1"), \
         patch("novel_review.storage.get_llm_config", return_value={"model": "test-model"}):
        yield Storage(base_dir=artifacts, resume=True, force=False)


@pytest.fixture
def force_storage(tmp_path):
    """force模式Storage"""
    artifacts = tmp_path / "artifacts"
    with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
         patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
         patch("novel_review.storage.get_prompt_version", return_value="v1"), \
         patch("novel_review.storage.get_llm_config", return_value={"model": "test-model"}):
        yield Storage(base_dir=artifacts, resume=True, force=True)


SAMPLE_DATA = {"chunk_id": 0, "char_range": [0, 100], "pacing_score": 3}


class TestResumeCache:
    def test_save_and_has_result(self, tmp_storage):
        """保存后has_result返回True"""
        tmp_storage.save_chunk_result("phase1_light", 0, SAMPLE_DATA)
        assert tmp_storage.has_result("phase1_light", 0)

    def test_missing_result_returns_false(self, tmp_storage):
        """未保存的块has_result返回False"""
        assert not tmp_storage.has_result("phase1_light", 99)

    def test_load_matches_saved(self, tmp_storage):
        """加载结果与保存内容一致"""
        tmp_storage.save_chunk_result("phase1_deep", 5, SAMPLE_DATA)
        loaded = tmp_storage.load_chunk_result("phase1_deep", 5)
        assert loaded == SAMPLE_DATA

    def test_load_missing_returns_none(self, tmp_storage):
        """加载不存在的块返回None"""
        assert tmp_storage.load_chunk_result("phase1_deep", 99) is None

    def test_force_ignores_cache(self, force_storage):
        """force模式下has_result始终返回False"""
        force_storage.save_chunk_result("phase1_light", 0, SAMPLE_DATA)
        assert not force_storage.has_result("phase1_light", 0)

    def test_force_but_load_still_works(self, force_storage):
        """force模式下save/load仍然正常工作"""
        force_storage.save_chunk_result("phase1_light", 0, SAMPLE_DATA)
        loaded = force_storage.load_chunk_result("phase1_light", 0)
        assert loaded == SAMPLE_DATA


class TestCacheInvalidation:
    def test_model_change_invalidates(self, tmp_path):
        """模型变化后旧缓存失效"""
        artifacts = tmp_path / "artifacts"

        # 用model-A保存
        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v1"), \
             patch("novel_review.storage.get_llm_config", return_value={"model": "model-A"}):
            s1 = Storage(base_dir=artifacts)
            s1.save_chunk_result("phase1_light", 0, SAMPLE_DATA)
            assert s1.has_result("phase1_light", 0)

        # 切换到model-B，缓存应失效
        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v1"), \
             patch("novel_review.storage.get_llm_config", return_value={"model": "model-B"}):
            s2 = Storage(base_dir=artifacts)
            assert not s2.has_result("phase1_light", 0)

    def test_prompt_version_change_invalidates(self, tmp_path):
        """prompt版本变化后旧缓存失效"""
        artifacts = tmp_path / "artifacts"

        # 用v1保存
        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v1"), \
             patch("novel_review.storage.get_llm_config", return_value={"model": "test"}):
            s1 = Storage(base_dir=artifacts)
            s1.save_chunk_result("phase1_deep", 0, SAMPLE_DATA)
            assert s1.has_result("phase1_deep", 0)

        # 切换到v2，缓存应失效
        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v2"), \
             patch("novel_review.storage.get_llm_config", return_value={"model": "test"}):
            s2 = Storage(base_dir=artifacts)
            assert not s2.has_result("phase1_deep", 0)

    def test_same_config_preserves_cache(self, tmp_path):
        """相同配置下缓存保持有效"""
        artifacts = tmp_path / "artifacts"
        cfg = {"model": "same-model"}

        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v1"), \
             patch("novel_review.storage.get_llm_config", return_value=cfg):
            s1 = Storage(base_dir=artifacts)
            s1.save_chunk_result("phase1_light", 3, SAMPLE_DATA)

        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v1"), \
             patch("novel_review.storage.get_llm_config", return_value=cfg):
            s2 = Storage(base_dir=artifacts)
            assert s2.has_result("phase1_light", 3)


class TestManifestAndJson:
    def test_save_and_load_manifest(self, tmp_storage):
        manifest = {"source_file": "test.txt", "total_chunks": 1, "chunks": []}
        tmp_storage.save_manifest(manifest)
        loaded = tmp_storage.load_manifest()
        assert loaded == manifest

    def test_load_missing_manifest(self, tmp_path):
        """无manifest时返回None"""
        artifacts = tmp_path / "empty"
        with patch("novel_review.storage.ARTIFACTS_DIR", artifacts), \
             patch("novel_review.storage.OUTPUT_DIR", tmp_path / "output"), \
             patch("novel_review.storage.get_prompt_version", return_value="v1"), \
             patch("novel_review.storage.get_llm_config", return_value={"model": "x"}):
            s = Storage(base_dir=artifacts)
            assert s.load_manifest() is None

    def test_save_json_to_output(self, tmp_storage):
        data = {"title": "test"}
        fp = tmp_storage.save_json("output/report.json", data)
        assert fp.exists()
        with open(fp, encoding="utf-8") as f:
            assert json.load(f) == data

    def test_save_text(self, tmp_storage):
        fp = tmp_storage.save_text("output/report.md", "# Test")
        assert fp.exists()
        assert fp.read_text(encoding="utf-8") == "# Test"
