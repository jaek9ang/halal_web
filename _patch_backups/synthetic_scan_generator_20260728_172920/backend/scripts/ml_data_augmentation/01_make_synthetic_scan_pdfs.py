from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError as exc:
    raise SystemExit(
        "PyMuPDF가 없습니다. 현재 .venv에 설치한 뒤 다시 실행하세요."
    ) from exc

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError as exc:
    raise SystemExit(
        "Pillow가 없습니다. 현재 .venv에 설치한 뒤 다시 실행하세요."
    ) from exc


VARIANT_PROFILES = [
    {
        "name": "SCAN_A_CLEAN",
        "dpi": 300,
        "jpeg_quality": 86,
        "max_rotation": 0.45,
        "blur_min": 0.05,
        "blur_max": 0.25,
        "contrast_min": 0.96,
        "contrast_max": 1.04,
        "brightness_min": 0.98,
        "brightness_max": 1.03,
        "noise_strength": 1.5,
        "grayscale_probability": 0.25,
    },
    {
        "name": "SCAN_B_OFFICE",
        "dpi": 220,
        "jpeg_quality": 74,
        "max_rotation": 1.20,
        "blur_min": 0.20,
        "blur_max": 0.65,
        "contrast_min": 0.88,
        "contrast_max": 1.08,
        "brightness_min": 0.94,
        "brightness_max": 1.04,
        "noise_strength": 4.0,
        "grayscale_probability": 0.70,
    },
    {
        "name": "SCAN_C_LOW",
        "dpi": 180,
        "jpeg_quality": 62,
        "max_rotation": 1.80,
        "blur_min": 0.40,
        "blur_max": 0.95,
        "contrast_min": 0.80,
        "contrast_max": 1.10,
        "brightness_min": 0.90,
        "brightness_max": 1.04,
        "noise_strength": 7.0,
        "grayscale_probability": 0.90,
    },
]


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def text_char_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as document:
        return sum(
            len(page.get_text("text").strip())
            for page in document
        )


def is_native_text_pdf(pdf_path: Path) -> bool:
    try:
        with fitz.open(pdf_path) as document:
            page_counts = [
                len(page.get_text("text").strip())
                for page in document
            ]

        if not page_counts:
            return False

        total = sum(page_counts)
        pages_with_text = sum(count >= 30 for count in page_counts)

        return (
            total >= 150
            and pages_with_text >= max(1, len(page_counts) // 2)
        )
    except Exception:
        return False


def read_validation_groups(runtime_root: Path) -> dict[str, str]:
    pointer = (
        runtime_root
        / "reports"
        / "latest_product_item_labels.txt"
    )

    if not pointer.exists():
        return {}

    report_root = Path(
        pointer.read_text(
            encoding="utf-8-sig"
        ).strip()
    )
    csv_path = (
        report_root
        / "01_document_structure_candidates.csv"
    )

    if not csv_path.exists():
        return {}

    mapping: dict[str, str] = {}

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            sha256 = clean(row.get("sha256")).upper()
            group = clean(row.get("validation_group"))

            if sha256 and group:
                mapping[sha256] = group

    return mapping


def add_scan_noise(
    image: Image.Image,
    strength: float,
    rng: random.Random,
) -> Image.Image:
    if strength <= 0:
        return image

    noise_seed = rng.randint(0, 2**31 - 1)
    random.seed(noise_seed)

    noise = Image.effect_noise(
        image.size,
        sigma=float(strength),
    ).convert("L")
    noise = ImageOps.autocontrast(noise)

    if image.mode != "RGB":
        image = image.convert("RGB")

    noise_rgb = Image.merge(
        "RGB",
        (noise, noise, noise),
    )

    alpha = min(
        0.12,
        max(0.01, strength / 100.0),
    )

    return Image.blend(
        image,
        noise_rgb,
        alpha,
    )


def rotate_on_white_canvas(
    image: Image.Image,
    angle: float,
) -> Image.Image:
    if abs(angle) < 0.01:
        return image

    original_size = image.size
    rotated = image.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor="white",
    )
    fitted = ImageOps.contain(
        rotated,
        original_size,
        method=Image.Resampling.LANCZOS,
    )

    canvas = Image.new(
        "RGB",
        original_size,
        "white",
    )
    left = (original_size[0] - fitted.width) // 2
    top = (original_size[1] - fitted.height) // 2
    canvas.paste(fitted, (left, top))

    return canvas


def process_page_image(
    image: Image.Image,
    profile: dict[str, Any],
    rng: random.Random,
) -> tuple[bytes, dict[str, Any]]:
    if image.mode != "RGB":
        image = image.convert("RGB")

    grayscale = (
        rng.random()
        < float(profile["grayscale_probability"])
    )

    if grayscale:
        image = ImageOps.grayscale(image).convert("RGB")

    contrast = rng.uniform(
        float(profile["contrast_min"]),
        float(profile["contrast_max"]),
    )
    brightness = rng.uniform(
        float(profile["brightness_min"]),
        float(profile["brightness_max"]),
    )
    blur = rng.uniform(
        float(profile["blur_min"]),
        float(profile["blur_max"]),
    )
    rotation = rng.uniform(
        -float(profile["max_rotation"]),
        float(profile["max_rotation"]),
    )

    image = ImageEnhance.Contrast(
        image
    ).enhance(contrast)
    image = ImageEnhance.Brightness(
        image
    ).enhance(brightness)

    if blur > 0.01:
        image = image.filter(
            ImageFilter.GaussianBlur(radius=blur)
        )

    image = add_scan_noise(
        image,
        float(profile["noise_strength"]),
        rng,
    )
    image = rotate_on_white_canvas(
        image,
        rotation,
    )

    stream = io.BytesIO()
    image.save(
        stream,
        format="JPEG",
        quality=int(profile["jpeg_quality"]),
        optimize=True,
        dpi=(
            int(profile["dpi"]),
            int(profile["dpi"]),
        ),
    )

    return stream.getvalue(), {
        "grayscale": grayscale,
        "contrast": round(contrast, 4),
        "brightness": round(brightness, 4),
        "blur_radius": round(blur, 4),
        "rotation_degrees": round(rotation, 4),
    }


def rasterize_pdf(
    source_path: Path,
    output_path: Path,
    profile: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    page_effects: list[dict[str, Any]] = []

    with fitz.open(source_path) as source:
        output = fitz.open()

        try:
            for page_index, page in enumerate(source):
                pixmap = page.get_pixmap(
                    dpi=int(profile["dpi"]),
                    colorspace=fitz.csRGB,
                    alpha=False,
                    annots=True,
                )

                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )

                jpeg_bytes, effects = process_page_image(
                    image,
                    profile,
                    rng,
                )

                target_page = output.new_page(
                    width=page.rect.width,
                    height=page.rect.height,
                )
                target_page.insert_image(
                    target_page.rect,
                    stream=jpeg_bytes,
                    keep_proportion=False,
                    overlay=True,
                )

                page_effects.append({
                    "page": page_index + 1,
                    **effects,
                })

            output.save(
                output_path,
                garbage=4,
                deflate=True,
                clean=True,
            )
        finally:
            output.close()

    text_count = text_char_count(output_path)

    return {
        "page_count": len(page_effects),
        "output_text_char_count": text_count,
        "is_image_only": text_count == 0,
        "page_effects": page_effects,
    }


def discover_candidates(
    input_root: Path,
    include_institutions: set[str],
    exclude_institutions: set[str],
) -> dict[str, list[Path]]:
    by_institution: dict[str, list[Path]] = defaultdict(list)

    for path in input_root.rglob("*.pdf"):
        relative = path.relative_to(input_root)
        institution = (
            relative.parts[0].upper()
            if len(relative.parts) > 1
            else "UNKNOWN"
        )

        if (
            include_institutions
            and institution not in include_institutions
        ):
            continue

        if institution in exclude_institutions:
            continue

        if not is_native_text_pdf(path):
            continue

        by_institution[institution].append(path)

    return by_institution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--max-per-institution", type=int, required=True)
    parser.add_argument("--variants-per-pdf", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--include-institutions",
        default="",
    )
    parser.add_argument(
        "--exclude-institutions",
        default="",
    )
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).resolve()
    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()

    include_institutions = {
        value.strip().upper()
        for value in args.include_institutions.split(",")
        if value.strip()
    }
    exclude_institutions = {
        value.strip().upper()
        for value in args.exclude_institutions.split(",")
        if value.strip()
    }

    if args.max_per_institution < 1:
        raise ValueError(
            "max-per-institution은 1 이상이어야 합니다."
        )

    if not 1 <= args.variants_per_pdf <= len(
        VARIANT_PROFILES
    ):
        raise ValueError(
            "variants-per-pdf는 1~3이어야 합니다."
        )

    output_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    validation_groups = read_validation_groups(
        runtime_root
    )
    candidates = discover_candidates(
        input_root,
        include_institutions,
        exclude_institutions,
    )

    selection_rng = random.Random(args.seed)
    selected: list[tuple[str, Path]] = []

    for institution in sorted(candidates):
        paths = sorted(candidates[institution])
        selection_rng.shuffle(paths)

        for path in paths[: args.max_per_institution]:
            selected.append((institution, path))

    manifest_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []

    for document_index, (
        institution,
        source_path,
    ) in enumerate(selected, start=1):
        source_sha = file_sha256(source_path)
        relative = source_path.relative_to(
            input_root
        )
        source_group = validation_groups.get(
            source_sha,
            f"{institution}::SOURCE::{source_sha[:16]}",
        )

        print(
            f"[{document_index}/{len(selected)}] "
            f"{institution} | {source_path.name}"
        )

        for variant_index in range(
            args.variants_per_pdf
        ):
            profile = VARIANT_PROFILES[variant_index]
            augmentation_id = (
                f"{source_sha[:12]}__"
                f"{profile['name']}__"
                f"S{args.seed}"
            )
            output_name = (
                f"{source_path.stem}"
                f"__SYNTH_{profile['name']}.pdf"
            )
            output_path = (
                output_root
                / institution
                / relative.parent.relative_to(
                    relative.parts[0]
                )
                / output_name
            )

            variant_seed = (
                args.seed
                + document_index * 1009
                + variant_index * 9176
            )

            try:
                result = rasterize_pdf(
                    source_path,
                    output_path,
                    profile,
                    variant_seed,
                )

                if not result["is_image_only"]:
                    raise RuntimeError(
                        "출력 PDF에 텍스트 레이어가 남았습니다."
                    )

                synthetic_sha = file_sha256(
                    output_path
                )

                manifest_rows.append({
                    "institution": institution,
                    "source_path": str(source_path),
                    "synthetic_path": str(output_path),
                    "source_sha256": source_sha,
                    "synthetic_sha256": synthetic_sha,
                    "source_document_id": source_sha,
                    "validation_group": source_group,
                    "augmentation_id": augmentation_id,
                    "augmentation_profile": profile["name"],
                    "seed": variant_seed,
                    "dpi": profile["dpi"],
                    "jpeg_quality": profile["jpeg_quality"],
                    "max_rotation": profile["max_rotation"],
                    "noise_strength": profile["noise_strength"],
                    "page_count": result["page_count"],
                    "output_text_char_count": (
                        result["output_text_char_count"]
                    ),
                    "is_image_only": (
                        result["is_image_only"]
                    ),
                    "page_effects_json": json.dumps(
                        result["page_effects"],
                        ensure_ascii=False,
                    ),
                })
            except Exception as exc:
                failure_rows.append({
                    "institution": institution,
                    "source_path": str(source_path),
                    "augmentation_profile": profile["name"],
                    "error": repr(exc),
                })
                print(
                    f"  실패: {profile['name']} | {exc}"
                )

    manifest_path = (
        output_root
        / "synthetic_scan_manifest.csv"
    )
    failure_path = (
        output_root
        / "synthetic_scan_failures.csv"
    )
    summary_path = (
        output_root
        / "synthetic_scan_summary.json"
    )

    manifest_columns = [
        "institution",
        "source_path",
        "synthetic_path",
        "source_sha256",
        "synthetic_sha256",
        "source_document_id",
        "validation_group",
        "augmentation_id",
        "augmentation_profile",
        "seed",
        "dpi",
        "jpeg_quality",
        "max_rotation",
        "noise_strength",
        "page_count",
        "output_text_char_count",
        "is_image_only",
        "page_effects_json",
    ]

    with manifest_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=manifest_columns,
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    with failure_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "institution",
                "source_path",
                "augmentation_profile",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(failure_rows)

    institution_counts = Counter(
        row["institution"]
        for row in manifest_rows
    )
    profile_counts = Counter(
        row["augmentation_profile"]
        for row in manifest_rows
    )

    summary = {
        "schema_version": "synthetic_scan_dataset_v1",
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "runtime_root": str(runtime_root),
        "input_root": str(input_root),
        "output_root": str(output_root),
        "seed": args.seed,
        "max_per_institution": (
            args.max_per_institution
        ),
        "variants_per_pdf": (
            args.variants_per_pdf
        ),
        "include_institutions": sorted(
            include_institutions
        ),
        "exclude_institutions": sorted(
            exclude_institutions
        ),
        "eligible_institution_count": len(
            candidates
        ),
        "selected_source_document_count": len(
            selected
        ),
        "generated_pdf_count": len(
            manifest_rows
        ),
        "failure_count": len(
            failure_rows
        ),
        "all_generated_pdfs_are_image_only": all(
            bool(row["is_image_only"])
            for row in manifest_rows
        ),
        "generated_by_institution": dict(
            institution_counts
        ),
        "generated_by_profile": dict(
            profile_counts
        ),
        "validation_rule": (
            "원본과 모든 합성본은 동일 validation_group을 사용해야 합니다."
        ),
        "training_rule": (
            "합성본은 학습 데이터 증강에만 사용하고, "
            "최종 독립 테스트에는 실제 PDF만 사용합니다."
        ),
    }

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("합성 스캔 PDF 생성 완료")
    print(
        f"선택 원본 문서 : "
        f"{summary['selected_source_document_count']}"
    )
    print(
        f"생성 PDF       : "
        f"{summary['generated_pdf_count']}"
    )
    print(
        f"실패           : "
        f"{summary['failure_count']}"
    )
    print(
        f"모두 이미지형  : "
        f"{summary['all_generated_pdfs_are_image_only']}"
    )
    print(f"출력 폴더      : {output_root}")
    print(f"매니페스트     : {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())