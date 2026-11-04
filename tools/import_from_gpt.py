"""Copy the useful subset of the old GPT project into assets/ as individual frames.

Run locally only (the source folder exists on the owner's PC, not in the cloud):
    python tools/import_from_gpt.py
The source folder is read, never modified.
"""
from pathlib import Path
import shutil
from PIL import Image

SRC = Path(r"C:\Users\ritwi\Desktop\gpt\Point and touch game\character_animation_demo")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CELL = (640, 576)


def split_sheet(sheet_path, dest, cols, rows, count, cell=CELL):
    sheet = Image.open(sheet_path).convert("RGBA")
    assert sheet.size == (cols * cell[0], rows * cell[1]), (sheet_path, sheet.size)
    dest.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        x, y = (i % cols) * cell[0], (i // cols) * cell[1]
        sheet.crop((x, y, x + cell[0], y + cell[1])).save(dest / f"{i + 1:02}.png")


def main():
    # Guard: 14-frame generated test, already split into frames by GPT.
    guard_frames = SRC / "guard_sprites" / "fourteen" / "frames"
    for action in sorted(p.name for p in guard_frames.iterdir() if p.is_dir()):
        shutil.copytree(guard_frames / action, OUT / "guard" / action, dirs_exist_ok=True)
    # Ladder down is ladder up reversed in the old project; keep that explicit in the manifest.
    shutil.copy(SRC / "guard_concepts" / "guard_silver_blue_concept.png", OUT / "guard" / "concept.png")

    rework = SRC / "sprite_rework"
    split_sheet(rework / "sheets" / "walk_keypose_test.png", OUT / "ren" / "walk_keypose", 4, 1, 4)
    (OUT / "ren" / "idle").mkdir(parents=True, exist_ok=True)
    shutil.copy(rework / "source" / "idle_walk_matched_cell.png", OUT / "ren" / "idle" / "01.png")
    split_sheet(rework / "sheets" / "jump.png", OUT / "ren" / "jump", 7, 2, 14)
    split_sheet(rework / "sheets" / "walk_fourteen_draft.png", OUT / "ren" / "rejected_walk_fourteen", 7, 2, 14)
    split_sheet(rework / "sheets" / "walk_flatboy_reference.png", OUT / "ren" / "rejected_walk_flatboy", 5, 3, 15)
    split_sheet(rework / "sheets" / "idle_walk_blink.png", OUT / "ren" / "unverified_idle_blink", 7, 2, 14)
    # First-pass reworked reactions: never individually reviewed by the owner.
    for name in ("happy", "interact", "hurt_stumble", "caught_game_over", "look_around", "ladder_up"):
        split_sheet(rework / "sheets" / f"{name}.png", OUT / "ren" / name, 7, 2, 14)
    # The liked grounded ledge climb uses smaller 512 x 448 cells.
    terra = SRC / "terra_demo"
    split_sheet(terra / "climb_grounded_up.png", OUT / "ren" / "climb_up", 7, 2, 14, (512, 448))
    split_sheet(terra / "climb_grounded_down.png", OUT / "ren" / "climb_down", 7, 2, 14, (512, 448))

    ref = OUT / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    shutil.copy(rework / "ren_identity_comparison.png", ref / "ren_identity_drift_example.png")
    shutil.copy(SRC.parent / "PROJECT_HISTORY_AND_ANIMATION_ENGINE_HANDOFF.md", ref / "GPT_HANDOFF.md")
    print("Imported assets into", OUT)


if __name__ == "__main__":
    main()
