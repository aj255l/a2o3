# Archiver for AO3
This is my personal Python script for downloading and archiving works from AO3.

## Work Skin Preservation
One of the main reasons this script exists is to preserve AO3 creator styles.

AO3 strips work skin information during its own ebook conversion flow. This script can preserve work skins by downloading HTML and converting it locally instead of relying on AO3's conversion output.

If preserving creator styles matters for a work, HTML is the safest format. You can also use `--preserve-creator-style` to keep work skins when downloading a non-HTML format.

## Usage
At the moment, authentication to AO3 is required and happens every time you run the script. If you don't want to be prompted for your username and password, the script can read them out of the environment variables `AO3_USERNAME` and `AO3_PASSWORD`, respectively.

To download a single work:
```bash
a2o3 archive --work <work_id>
```

To download multiple specific works:
```bash
a2o3 archive --works <work_id> <work_id> ...
```

To download all works from an author:
```bash
a2o3 archive --user <username>
```

To specify an output directory, use the `--output` flag. If you provide a path to a directory that already exists, the works will be written to `<output>/archive`. Otherwise, the directory will be created and works will be written directly to it.

## Planned Features
* update metadata so Calibre can sort by fandom
* update stylesheets so Homestuck work skin works
