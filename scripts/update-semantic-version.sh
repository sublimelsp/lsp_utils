#!/usr/bin/env bash

GITHUB_REPO_URL="https://github.com/rbarrois/python-semanticversion"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_DIR="${SCRIPT_DIR}/../st4_py38/lsp_utils/third_party"
PACKAGE_NAME="semantic_version"

# -------- #
# clean up #
# -------- #

pushd "${OUTPUT_DIR}" || exit

rm -rf "${PACKAGE_NAME}" temp

popd || exit

# ---------------- #
# clone repo       #
# ---------------- #

pushd "${OUTPUT_DIR}" || exit

echo 'Enter commit SHA, branch or tag (for example 2.1.0) to build'
read -rp 'SHA, branch or tag (default: master): ' ref

if [ "${ref}" = "" ]; then
    ref="master"
fi

echo "Cloning ${GITHUB_REPO_URL}"
git clone ${GITHUB_REPO_URL} --branch ${ref} --single-branch "${OUTPUT_DIR}/temp" || echo "Repo already cloned. Continuing..."
current_sha=$( git rev-parse HEAD )
printf "ref: %s\n%s\n" "$ref" "$current_sha" > update-info.log

popd || exit

# ------------- #
# apply patches #
# ------------- #

pushd "${OUTPUT_DIR}/temp" || exit

git am "${SCRIPT_DIR}/3.3-compat-fix.patch" || exit
rm semantic_version/django_fields.py || exit

popd || exit

# -------------------- #
# collect output files #
# -------------------- #

pushd "${OUTPUT_DIR}" || exit

echo 'Moving and cleaning up files...'
mv temp/semantic_version/ "${OUTPUT_DIR}/"
mv temp/LICENSE "${OUTPUT_DIR}/${PACKAGE_NAME}/"
mv temp/README.rst "${OUTPUT_DIR}/${PACKAGE_NAME}/"
rm -rf "${OUTPUT_DIR}/temp"

popd || exit
