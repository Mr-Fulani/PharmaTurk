#!/bin/bash

echo "Generating JSON serializable models..."

dart run build_runner build --delete-conflicting-outputs

echo "Done!"
