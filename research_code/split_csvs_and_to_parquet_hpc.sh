#!/bin/bash
#SBATCH --partition=cpu-single
#SBATCH --cpus-per-task=16
#SBATCH --mem=64gb
#SBATCH --time=96:00:00

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_BIN="python"

# Load configuration through start.py
eval "$($PYTHON_BIN - <<'PY'
import os
from start import load_config

cfg = load_config(script_name='csv_to_parquet')

print(f'export input_dir="{os.path.abspath(cfg["paths"]["raw_metadata_dir"])}"')
print(f'export outdir="{os.path.abspath(cfg["paths"]["splitted_raw_metadata_dir"])}"')
print(f'export n_rows={cfg["csv_split_params"]["n_rows"]}')
print(f'export split_enabled="{str(cfg["csv_split_params"]["split_enabled"]).lower()}"')
print(f'export updated_after="{cfg["csv_split_params"]["updated_after"]}"')
PY
)"

echo "DEBUG: split_enabled='$split_enabled', n_rows='$n_rows'"

mkdir -p "$outdir"

for input in $(find "$input_dir" -type f -name 'metadata_unfiltered_*.csv' -newermt "$updated_after"); do
    filename=$(basename "$input")
    name="${filename%.csv}"
    prefix="splitted_${name}"
    pattern="$outdir/${prefix}_*.csv"

    echo "➡️ Processing $filename"

    # Check for existing split files
    existing_files=( $pattern )
    if [ -e "${existing_files[0]}" ]; then
        num_existing=$(( ${#existing_files[@]} - 1 ))
        start_row=$(( num_existing * n_rows + 2 ))  # +2 to skip header once
        echo "🔁 Resuming from line $start_row (found $num_existing existing split files)"
    else
        num_existing=0
        start_row=2
        echo "🆕 No existing split files found — starting from the beginning"
    fi

    if [ "$split_enabled" = "true" ]; then
        header=$(head -n 1 "$input")

        # Start from the correct row
        tail -n +"$start_row" "$input" | split -d -l "$n_rows" - "$outdir/${prefix}_tmp_"

        # Rename temporary splits with correct sequence numbers
        next_index=$(printf "%04d" "$num_existing")
        for f in "$outdir"/${prefix}_tmp_*; do
            new_name="${outdir}/${prefix}_${next_index}.csv"
            echo "$header" | cat - "$f" > "$new_name"
            rm "$f"
            next_index=$(printf "%04d" $((10#$next_index + 1)))
        done

        echo "✅ Split complete/resumed for $filename. Files saved to: $outdir"
    else
        echo "ℹ️ Skipping splitting for $filename because split_enabled=$split_enabled"
    fi

    # Extract tile name from filename (e.g., metadata_unfiltered_158-137-8.csv -> 158-137-8)
    tile_name=$(echo "$name" | sed 's/^metadata_unfiltered_//')
    $PYTHON_BIN csv_to_parquet.py "$tile_name"
    if [ $? -ne 0 ]; then
        echo "❌ ERROR: Failed to convert $filename to Parquet"
        exit 1
    fi
    echo "✅ Converting $filename from .csv to .parquet is complete"
done
