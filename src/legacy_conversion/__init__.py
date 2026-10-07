"""legacy_conversion: the one removable module that converts an old install's files into a
plan file (design F section 8; master plan WP10 assembles it, WP11.6 deletes it).

Each work package that moves a dataset writes its conversion step under ``steps/`` as a
documented, tested unit; nothing here is wired into startup until WP10. Steps read the
old files only through ``src/csv_exchange`` and never modify or delete an original.
"""
