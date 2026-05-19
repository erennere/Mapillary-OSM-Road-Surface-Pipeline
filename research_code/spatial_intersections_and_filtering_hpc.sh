#!/bin/bash
#SBATCH --partition=single
#SBATCH --error=errors_%A_%a.err
#SBATCH --output=outputs_%A_%a.out
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=8
#SBATCH --mem=16gb
#SBATCH --time=96:00:00

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Find Python executable
if command -v python &> /dev/null; then
    PYTHON_BIN="python"
elif command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
else
    echo "❌ Python not found in PATH"
    exit 1
fi

# Load configuration through start.py
eval "$($PYTHON_BIN - <<'PY'
import os
from start import load_config

cfg = load_config(script_name='metadata_intersections_and_filtering')

print(f'export DATA_DIR="{os.path.abspath(cfg["paths"]["tile_partitioned_parquet_raw_metadata_dir"])}"')
print(f'export ZOOM_LEVEL={cfg["params"]["zoom_level"]}')
print(f'export URBAN_THRESHOLD={cfg["params"]["urban_threshold"]}')
print(f'export RURAL_THRESHOLD={cfg["params"]["rural_threshold"]}')
print(f'export UPDATED_AFTER="{cfg["metadata_params"]["updated_after"]}"')
PY
)"

echo "DEBUG: DATA_DIR='$DATA_DIR', ZOOM_LEVEL=$ZOOM_LEVEL, URBAN_THRESHOLD=$URBAN_THRESHOLD, RURAL_THRESHOLD=$RURAL_THRESHOLD, UPDATED_AFTER='$UPDATED_AFTER'"

# Extract exclude patterns (optional)
EXCLUDE_PATTERNS="example_to_skip,bad_file_prefix"

# ————————————————————————
# BUILD FILE LIST
# ————————————————————————
EXCLUDE_REGEX=$(echo "$EXCLUDE_PATTERNS" | sed 's/,/|/g')
mapfile -t files < <(
    find "$DATA_DIR" -type f -name "*.parquet" -newermt "$UPDATED_AFTER" \
    | grep -E "tile=" \
    | grep -Ev "$EXCLUDE_REGEX" \
    | sort
)

echo "✅ Found ${#files[@]} parquet files to process"

# ————————————————————————
# SELF-SUBMIT LOGIC (LOGIN NODE)
# ————————————————————————
if [ -z "$SLURM_ARRAY_TASK_ID" ] && command -v sbatch >/dev/null 2>&1; then
    N=${#files[@]}
    echo "🔍 Detected $N valid parquet files."
    echo "📤 Submitting SLURM array job..."
    sbatch --array=0-$((N-1)) "$0"
    exit 0
fi

# ————————————————————————
# RUN JOB
# ————————————————————————
if [ -n "$SLURM_ARRAY_TASK_ID" ]; then
    # Running on HPC as SLURM array task
    file="${files[$SLURM_ARRAY_TASK_ID]}"
    echo "🚀 SLURM task $SLURM_ARRAY_TASK_ID processing $file at $(date)"
    $PYTHON_BIN metadata_intersections_and_filtering.py "$file"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Successfully processed: $file at $(date)"
    else
        echo "❌ Failed to process: $file (exit code: $EXIT_CODE) at $(date)"
        exit $EXIT_CODE
    fi
else
    # Running locally: detect CPU cores and run dynamically
    CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
    # Limit parallelism to avoid memory exhaustion (geographic data is memory-intensive)
    MAX_PARALLEL=6
    PARALLEL_JOBS=$((CPU_CORES < MAX_PARALLEL ? CPU_CORES : MAX_PARALLEL))
    echo "💻 Running locally on $CPU_CORES cores (using max $PARALLEL_JOBS parallel jobs for memory efficiency)"

    running_pids=()
    failed_count=0
    
    for idx in "${!files[@]}"; do
        file="${files[$idx]}"
        echo "📄 [$((idx+1))/${#files[@]}] Starting $file at $(date)"
        $PYTHON_BIN metadata_intersections_and_filtering.py "$file" &

        running_pids+=($!)

        while [ ${#running_pids[@]} -ge $PARALLEL_JOBS ]; do
            if wait -n 2>/dev/null; then
                if [ $? -ne 0 ]; then
                    ((failed_count++))
                fi
                tmp=()
                for pid in "${running_pids[@]}"; do
                    if kill -0 "$pid" 2>/dev/null; then
                        tmp+=("$pid")
                    fi
                done
                running_pids=("${tmp[@]}")
            else
                wait
                running_pids=()
            fi
        done
    done
    
    # Wait for remaining processes
    echo "⏳ Waiting for remaining processes..."
    for pid in "${running_pids[@]}"; do
        if ! wait "$pid"; then
            ((failed_count++))
        fi
    done
    
    if [ $failed_count -gt 0 ]; then
        echo "❌ $failed_count files failed to process"
        exit 1
    else
        echo "✅ All files processed successfully"
    fi

    # Wait for remaining jobs
    wait
    echo "✅ All files processed locally at $(date)"
fi
