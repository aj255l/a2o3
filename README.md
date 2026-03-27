# Archiver for AO3
This is my personal Python script for archiving AO3.

## BIG FAT WARNING
It turns out that AO3 strips work skin information during the conversion to EPUB! This means if you are downloading anything that uses a creator style, you should download it as HTML.

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
