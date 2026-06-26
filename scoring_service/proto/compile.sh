#!/bin/bash
cd "$(dirname "$0")"
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. scoring.proto
