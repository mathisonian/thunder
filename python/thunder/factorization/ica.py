"""
Class and standalone app for Independent Component Analysis
"""

import os
import argparse
import glob
from numpy import random, sqrt, zeros, real, dot, outer, diag, transpose
from scipy.linalg import sqrtm, inv, orth
from thunder.io import load
from thunder.io import save
from thunder.factorization import SVD
from thunder.util.matrices import RowMatrix
from pyspark import SparkContext


class ICA(object):
    """
    Independent component analysis on a dense matrix
    with initial dimensionality reduction via SVD

    Parameters
    ----------
    k : int
        Number of principal components to use

    c : int
        Number of independent components to estimate

    svdmethod : string, optional, default = "direct"
        Which SVD method to use

    maxiter : Int, optional, default = 10
        Maximum number of iterations

    tol : float, optional, default = 0.00001
        Tolerance for convergence

    Attributes
    ----------
    `w` : array, shape (c, ncols)
        Recovered mixing matrix

    `sigs` : RDD of nrows (tuple, array) pairs, each array of shape (c,)
        Estimated independent components
    """

    def __init__(self, k, c, svdmethod="direct", maxiter=10, tol=0.000001, seed=0):
        if c > k:
            raise Exception("number of independent comps " + str(c) +
                            " must be less than the number of principal comps " + str(k))
        self.k = k
        self.c = c
        self.svdmethod = svdmethod
        self.maxiter = maxiter
        self.tol = tol
        self.seed = seed

    def fit(self, data):
        """
        Fit independent components using an iterative fixed-point algorithm

        Parameters
        ----------
        data: RDD of (tuple, array) pairs, or RowMatrix
            Data to estimate independent components from

        Returns
        ----------
        self : returns an instance of self.
        """

        if type(data) is not RowMatrix:
            data = RowMatrix(data)

        # reduce dimensionality
        svd = SVD(k=self.k, method=self.svdmethod).calc(data)

        # whiten data
        whtmat = real(dot(inv(diag(svd.s/sqrt(data.nrows))), svd.v))
        unwhtmat = real(dot(transpose(svd.v), diag(svd.s/sqrt(data.nrows))))
        wht = data.times(whtmat.T)

        # do multiple independent component extraction
        if self.seed != 0:
            random.seed(self.seed)
        b = orth(random.randn(self.k, self.c))
        b_old = zeros((self.k, self.c))
        iter = 0
        minabscos = 0
        errvec = zeros(self.maxiter)

        while (iter < self.maxiter) & ((1 - minabscos) > self.tol):
            iter += 1
            # update rule for pow3 non-linearity (TODO: add others)
            b = wht.rows().map(lambda x: outer(x, dot(x, b) ** 3)).sum() / wht.nrows - 3 * b
            # make orthogonal
            b = dot(b, real(sqrtm(inv(dot(transpose(b), b)))))
            # evaluate error
            minabscos = min(abs(diag(dot(transpose(b), b_old))))
            # store results
            b_old = b
            errvec[iter-1] = (1 - minabscos)

        # get un-mixing matrix
        w = dot(transpose(b), whtmat)

        # get components
        sigs = data.times(w.T).rdd

        self.w = w
        self.sigs = sigs

        return self


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="do independent components analysis")
    parser.add_argument("master", type=str)
    parser.add_argument("datafile", type=str)
    parser.add_argument("outputdir", type=str)
    parser.add_argument("k", type=int)
    parser.add_argument("c", type=int)
    parser.add_argument("--svdmethod", choices=("direct", "em"), default="direct", required=False)
    parser.add_argument("--maxiter", type=float, default=100, required=False)
    parser.add_argument("--tol", type=float, default=0.000001, required=False)
    parser.add_argument("--preprocess", choices=("raw", "dff", "dff-highpass", "sub"), default="raw", required=False)
    parser.add_argument("--seed", type=int, default=0, required=False)

    args = parser.parse_args()
    
    sc = SparkContext(args.master, "ica")

    if args.master != "local":
        egg = glob.glob(os.path.join(os.environ['THUNDER_EGG'], "*.egg"))
        sc.addPyFile(egg[0])
    
    data = load(sc, args.datafile, args.preprocess).cache()
    result = ICA(args.k, args.c, args.svdmethod, args.maxiter, args.tol, args.seed).fit(data)

    outputdir = args.outputdir + "-ica"
    save(result.w, outputdir, "w", "matlab")
    save(result.sigs, outputdir, "sigs", "matlab")
