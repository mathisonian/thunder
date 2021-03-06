"""
Standalone app for mass-univariate classification
"""

import os
import argparse
import glob
from numpy import array
from thunder.classification import MassUnivariateClassifier
from thunder.io import load
from thunder.io import save
from pyspark import SparkContext


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="fit a regression model")
    parser.add_argument("master", type=str)
    parser.add_argument("datafile", type=str)
    parser.add_argument("paramfile", type=str)
    parser.add_argument("outputdir", type=str)
    parser.add_argument("classifymode", choices="naivebayes", help="form of classifier")
    parser.add_argument("--featureset", type=array, default="None", required=False)
    parser.add_argument("--cv", type=int, default="0", required=False)
    parser.add_argument("--preprocess", choices=("raw", "dff", "dff-highpass", "sub"), default="raw", required=False)

    args = parser.parse_args()

    sc = SparkContext(args.master, "classify")

    if args.master != "local":
        egg = glob.glob(os.path.join(os.environ['THUNDER_EGG'], "*.egg"))
        sc.addPyFile(egg[0])

    data = load(sc, args.datafile, args.preprocess)
    clf = MassUnivariateClassifier.load(args.paramfile, args.classifymode, cv=args.cv)
    perf = clf.classify(data, args.featureset)

    outputdir = args.outputdir + "-classify"
    save(perf, outputdir, "perf", "matlab")
