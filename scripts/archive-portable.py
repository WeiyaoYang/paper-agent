"""Archive only application payload, never runtime files produced during verification."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
parser.add_argument("archive", type=Path)
parser.add_argument("--public", action="store_true")
args = parser.parse_args()
allowed_folders = {"_internal", "schemas", "prompts", "behaviors", "templates", "assets"}
allowed_files = {"AgentWorkbench.exe", "README.txt", "config/model.toml", "config/planning.toml", "config/.env.example"}
with ZipFile(args.archive, "w", compression=ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
    for path in sorted(args.folder.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(args.folder)
        if relative.parts[0] not in allowed_folders and relative.as_posix() not in allowed_files:
            continue
        if args.public and relative.parts[0] == "assets" and path.name != "default-agent.svg":
            continue
        archive.write(path, "AgentWorkbench/" + relative.as_posix())
print(args.archive)
