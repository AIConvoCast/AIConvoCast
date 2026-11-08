#!/usr/bin/env bash
# Install ffmpeg from Ubuntu's packages, as the workflows always have.
#
# The runner's default mirror (azure.archive.ubuntu.com) is sometimes so slow that
# the download outlasts the job. If fetching takes longer than
# FFMPEG_FIRST_TRY_SECONDS (default 180), fetch once more from archive.ubuntu.com.
# Only the download is timed, so dpkg is never interrupted mid-install.
set -euo pipefail

first_try="${FFMPEG_FIRST_TRY_SECONDS:-180}"

fetch() {
  sudo apt-get -o Acquire::Retries=3 update
  sudo apt-get -o Acquire::Retries=3 install -y --download-only ffmpeg
}

if ! timeout "$first_try" bash -c "set -euo pipefail; $(declare -f fetch); fetch"; then
  echo  # apt may have been cut off mid-line; a workflow command must start a line
  echo "::warning::Fetching ffmpeg took over ${first_try}s or failed; retrying from archive.ubuntu.com."
  for file in /etc/apt/apt-mirrors.txt /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    if [ -f "$file" ]; then
      sudo sed -i 's#https\?://azure\.archive\.ubuntu\.com#http://archive.ubuntu.com#g' "$file"
    fi
  done
  fetch
fi

sudo apt-get install -y ffmpeg
ffmpeg -hide_banner -version | head -n 1
