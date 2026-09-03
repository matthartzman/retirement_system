"""src/parsing/ — siblings extracted from the former monolithic src/data_io.py.

System review 2026-08-31, finding A5 / Wave 3 item 3.13: split parse_client
into src/parsing/ siblings; move validation out. This package holds those
extracted pieces one section at a time (golden master green after each), so
it starts small and grows as further sections are pulled out of
src/data_io.py's parse_client()/build_plan_from_json().
"""
