import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from bilibili_daily import (
    advance_after_verification,
    build_clip_command,
    build_publish_command,
    cache_matches,
    create_cover,
    create_slide,
    fingerprint,
    load_contract,
    record_cache,
    thumbnail_transport_ready,
    transition_state,
    validate_contract,
    validate_date,
    validate_media_probe,
    write_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "content/2026-07-17-shield-machine.json"


class PipelineTests(unittest.TestCase):
    def test_contract_is_single_topic_bilibili_edition(self):
        contract = load_contract(CONTRACT)
        validate_contract(contract)
        self.assertEqual(contract["tid"], 232)
        self.assertEqual(len(contract["segments"]), 5)
        self.assertEqual(contract["target_duration_seconds"], [120, 240])
        self.assertTrue(contract["title"].endswith("｜每日新中国"))
        self.assertNotIn("欢迎收看", contract["segments"][0]["narration"][:60])
        self.assertEqual(contract["state_ceiling"], "awaiting_user_confirmation")
        self.assertTrue(Path(contract["source_file"]).is_file())

    def test_cover_is_1920_by_1080(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            background = temp / "background.png"
            output = temp / "cover.png"
            Image.new("RGB", (640, 960), (40, 80, 120)).save(background)
            create_cover(background, output, "14米盾构机\n穿越太湖")
            with Image.open(output) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertEqual(image.mode, "RGB")
                self.assertNotEqual(image.getpixel((960, 540)), (40, 80, 120))

    def test_phase_one_state_cannot_cross_confirmation_gate(self):
        self.assertEqual(
            transition_state("offline_verified", "awaiting_user_confirmation"),
            "awaiting_user_confirmation",
        )
        with self.assertRaises(ValueError):
            transition_state("awaiting_user_confirmation", "submitted_unverified")

    def test_manifest_hashes_artifacts_and_publish_preview_is_non_executing(self):
        contract = load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            video = temp / "video.mp4"
            cover = temp / "cover.png"
            audio = temp / "audio.mp3"
            video.write_bytes(b"video")
            cover.write_bytes(b"cover")
            audio.write_bytes(b"audio")
            manifest_path = temp / "manifest.json"
            manifest = write_manifest(
                contract,
                manifest_path,
                state="awaiting_user_confirmation",
                artifacts={"video": video, "cover": cover, "audio": audio},
            )
            self.assertEqual(len(manifest["artifacts"]["video"]["sha256"]), 64)
            command = build_publish_command(manifest_path)
            self.assertEqual(command[:3], ["sau", "bilibili", "upload-video"])
            self.assertIn("--thumbnail", command)
            self.assertIn(str(cover.resolve()), command)
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["state"], "awaiting_user_confirmation")

    def test_publish_preview_rejects_unverified_manifest(self):
        contract = load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            video = temp / "video.mp4"
            cover = temp / "cover.png"
            audio = temp / "audio.mp3"
            for path in (video, cover, audio):
                path.write_bytes(path.name.encode())
            manifest_path = temp / "manifest.json"
            write_manifest(
                contract,
                manifest_path,
                state="rendered",
                artifacts={"video": video, "cover": cover, "audio": audio},
            )
            with self.assertRaises(ValueError):
                build_publish_command(manifest_path)

    def test_publish_preview_rejects_tampered_state_ceiling(self):
        contract = load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            video = temp / "video.mp4"
            cover = temp / "cover.png"
            audio = temp / "audio.mp3"
            for path in (video, cover, audio):
                path.write_bytes(path.name.encode())
            manifest_path = temp / "manifest.json"
            manifest = write_manifest(
                contract,
                manifest_path,
                state="awaiting_user_confirmation",
                artifacts={"video": video, "cover": cover, "audio": audio},
            )
            manifest["state_ceiling"] = "public_verified"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_publish_command(manifest_path)

    def test_slide_is_horizontal_and_contains_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            background = temp / "background.png"
            output = temp / "slide.png"
            Image.new("RGB", (941, 1672), (10, 30, 70)).save(background)
            create_slide(background, output, "开挖直径 14.02米", 1, 5)
            with Image.open(output) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertNotEqual(image.getpixel((100, 900)), (10, 30, 70))

    def test_clip_command_uses_audio_as_duration_source(self):
        command = build_clip_command(Path("slide.png"), Path("audio.mp3"), Path("clip.mp4"))
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("-loop", command)
        self.assertIn("-shortest", command)
        self.assertIn("libx264", command)
        self.assertIn("aac", command)

    def test_media_probe_requires_horizontal_h264_aac_and_target_duration(self):
        probe = {
            "format": {"duration": "155.2"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        validate_media_probe(probe, [120, 240])
        bad = json.loads(json.dumps(probe))
        bad["streams"][0]["width"] = 1080
        bad["streams"][0]["height"] = 1920
        with self.assertRaises(ValueError):
            validate_media_probe(bad, [120, 240])
        bad_fps = json.loads(json.dumps(probe))
        bad_fps["streams"][0]["r_frame_rate"] = "25/1"
        with self.assertRaises(ValueError):
            validate_media_probe(bad_fps, [120, 240])

    def test_date_rejects_path_traversal(self):
        self.assertEqual(validate_date("2026-07-17"), "2026-07-17")
        for value in ("../content", "2026-7-17", "2026-02-30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_date(value)

    def test_thumbnail_transport_requires_real_sau_flag(self):
        self.assertTrue(thumbnail_transport_ready("usage: sau ... [--thumbnail THUMBNAIL]"))
        self.assertFalse(thumbnail_transport_ready("usage: sau ... [--schedule SCHEDULE]"))

    def test_verification_state_transition_is_idempotent(self):
        self.assertEqual(advance_after_verification("rendered"), "awaiting_user_confirmation")
        self.assertEqual(
            advance_after_verification("awaiting_user_confirmation"),
            "awaiting_user_confirmation",
        )
        with self.assertRaises(ValueError):
            advance_after_verification("planned")

    def test_cache_is_bound_to_input_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            artifact = temp / "audio.mp3"
            metadata = temp / "audio.sha256"
            artifact.write_bytes(b"audio")
            expected = fingerprint("hello", "voice", "+10%")
            record_cache(metadata, expected)
            self.assertTrue(cache_matches(artifact, metadata, expected))
            self.assertFalse(cache_matches(artifact, metadata, fingerprint("changed", "voice", "+10%")))


if __name__ == "__main__":
    unittest.main()
