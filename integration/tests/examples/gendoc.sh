#!/bin/bash

pushd ../../apidocs
mvn clean
mvn generate-sources

popd

