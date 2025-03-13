#!/usr/bin/env python3
# Copyright © 2025 Jonathan Tremesaygues <jonathan.tremesaygues@sereema.com>
# This work is free. You can redistribute it and/or modify it under the
# terms of the Do What The Fuck You Want To Public License, Version 2,
# as published by Sam Hocevar. See http://www.wtfpl.net/ for more details.
from argparse import ArgumentParser
from collections.abc import Sequence
from hashlib import sha256
from itertools import product
from pathlib import Path
from typing import Optional

import pandas as pd
from requests import Session
from tqdm import tqdm

type Filename = str
type Url = str
type Checksum = str
type DatasetEntry = tuple[Filename, Url, Checksum]


dataset_entries: tuple[DatasetEntry] = (
    (
        "scada_2016.xlsx",
        "https://www.edp.com/sites/default/files/2023-04/Wind-Turbine-SCADA-signals-2016.xlsx",
        "8caf93d656867c23b8a65f37d5ea13ba6e6b84e409d7162bcf0521e8f8993c1f",
    ),
    (
        "scada_2017.xlsx",
        "https://www.edp.com/sites/default/files/2023-04/Wind-Turbine-SCADA-signals-2017_0.xlsx",
        "32008fbb8527201c574b3b524ae396a96678c62e3abea529c83197e34f5ec1a8",
    ),
)

OUT_DIR: Path = Path(__file__).parent
CHUNK_SIZE: int = 4096


def main(args: Optional[Sequence[str]] = None) -> None:
    parser = ArgumentParser(description="Generate EDP dataset")
    parser.add_argument("-k", "--keep-downloaded-files", action="store_true")
    args = parser.parse_args(args)

    # Download datasets
    with Session() as session:
        for filename, url, checksum in tqdm(dataset_entries, "Downloading datasets…"):
            # Ignore already downloaded files
            output_file = OUT_DIR / filename
            if (
                output_file.exists()
                and sha256(output_file.read_bytes()).hexdigest() == checksum
            ):
                continue

            with session.get(url, stream=True) as response:
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", 0))

                with output_file.open("wb") as f:
                    for chunk in tqdm(
                        response.iter_content(chunk_size=CHUNK_SIZE),
                        total=content_length // CHUNK_SIZE,
                        unit="KB",
                        desc=f"Downloading {filename}…",
                        leave=False,
                    ):
                        f.write(chunk)

    # Open datasets
    dataframes = []
    for filename, _, _ in tqdm(dataset_entries, "Opening datasets…"):
        dataframes.append(pd.read_excel(OUT_DIR / filename, parse_dates=["Timestamp"]))

    # Merge datasets
    tqdm.write("Merging datasets…")
    dataframe = pd.concat(dataframes, ignore_index=True)
    del dataframes

    # Sort dataframe
    dataframe = dataframe.sort_values(by=["Timestamp", "Turbine_ID"])

    # Split datasets per year and turbines
    tqdm.write("Splitting datasets…")
    years = pd.unique(dataframe["Timestamp"].dt.year)
    turbines_ids = pd.unique(dataframe["Turbine_ID"])
    for turbine_id, year in tqdm(product(turbines_ids, years), "Saving datasets…"):
        mask_year = dataframe["Timestamp"].dt.year == year
        mask_turbine = dataframe["Turbine_ID"] == turbine_id
        mask = mask_year & mask_turbine
        split_dataframe = dataframe[mask]

        output_file = OUT_DIR / f"scada_{turbine_id}_{year}.csv"
        split_dataframe.to_csv(output_file, index=False)

    # Remove downloaded files
    if not args.keep_downloaded_files:
        for filename, _, _ in tqdm(dataset_entries, "Removing downloaded files…"):
            try:
                (OUT_DIR / filename).unlink()
            except Exception:
                pass


if __name__ == "__main__":
    main()
