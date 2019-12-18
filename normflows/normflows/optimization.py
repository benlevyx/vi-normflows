from tqdm import tqdm

from autograd import numpy as np
from autograd.numpy import random as npr
from autograd import grad
from autograd.misc.optimizers import adam, rmsprop
import matplotlib.pyplot as plt

from .flows import planar_flow
from .distributions import sample_from_pz, make_samples_z
from .plotting import plot_samples, plot_obs_latent, plot_mnist
from .nn_models import nn
from .config import figname
from .utils import clear_figs, get_samples_from_params, compare_reconstruction
from.transformations import affine


rs = npr.RandomState(0)
clear_figs()


def gradient_create(F, D, N, unpack_params):
    """Create variational objective, gradient, and parameter unpacking function

    Arguments:
        F {callable} -- Energy function (to be minimized)
        D {int} -- dimension of latent variables
        N {int} -- Number of samples to draw
        unpack_params {callable} -- Parameter unpacking function

    Returns
        'variational_objective', 'gradient', 'unpack_params'
    """

    def variational_objective(params, t):
        phi, theta = unpack_params(params)
        z0 = rs.randn(N, D)  # Gaussian noise here. Will add back in mu and sigma in F
        free_energy = F(z0, phi, theta, t)
        return free_energy

    gradient = grad(variational_objective)

    return variational_objective, gradient


def optimize(logp, X, D, K, N, init_params,
             unpack_params, encode, decode,
             max_iter, step_size, verbose=True):
    """Run the optimization for a mixture of Gaussians

    Arguments:
        logp {callable} -- Joint log-density of Z and X
        X {np.ndarray} -- Observed data
        D {int} -- Dimension of Z
        G {int} -- Number of Gaussians in GMM
        N {int} -- Number of samples to draw
        K {int} -- Number of flows
        max_iter {int} -- Maximum iterations of optimization
        step_size {float} -- Learning rate for optimizer
    """
    def logq0(z):
        """Just a standard Gaussian
        """
        return -D / 2 * np.log(2 * np.pi) - 0.5 * np.sum(z ** 2, axis=0)

    def hprime(x):
        return 1 - np.tanh(x) ** 2

    logdet_jac = lambda w, z, b: np.sum(w * hprime(np.sum(w * z, axis=1) + b).reshape(-1, 1), axis=1)

    def F(z0, phi, theta, t):
        eps = 1e-7
        mu0, log_sigma_diag0, W, U, B = encode(phi, X)
        cooling_max = np.min(np.array([max_iter / 2, 10000]))
        beta_t = np.min(np.array([1, 0.001 + t / cooling_max]))

        sd = np.sqrt(np.exp(log_sigma_diag0))
        zk = z0 * sd + mu0
        # Unsure if this should be z0 or z1 (after adding back in mean and sd)
        first = np.mean(logq0(z0))


        running_sum = 0.
        for k in range(K):
            w, u, b = W[k], U[k], B[k]
            #TODO: Get these to work with flow params in the shape (K, N, D)
            ldj = logdet_jac(w, zk, b)
            # print(f"ldj: {ldj}")
            ldj_dotprod = np.sum(u * ldj.reshape(-1, 1), axis=1)
            # print(f"ldj-dotprod: {ldj_dotprod}")
            ldj_abs = np.abs(1. + ldj_dotprod)
            # print(f"ldj-abs: {ldj_abs}")
            delta = np.log(eps + ldj_abs)
            # print(f"delta: {delta}")
            running_sum = running_sum + delta
            zk = planar_flow(zk, w, u, b)
        third = np.mean(running_sum)

        logits = decode(theta, zk)

        second = np.mean(logp(X, zk, logits))
        # second = np.mean(logp(X, zk, theta)) * beta_t  # Play with temperature

        # return first - second - third
        return first - second - third

    objective, gradient = gradient_create(F, D, N, unpack_params)
    pbar = tqdm(total=max_iter)

    def callback(params, t, g):
        pbar.update()
        if verbose:
            if t % 100 == 0:
                grad_mag = np.linalg.norm(gradient(params, t))
                tqdm.write(f"Iteration {t}; objective: {objective(params, t)} gradient mag: {grad_mag:.3f}")
            if t % 200 == 0:

                Xtrue = X[101].reshape(1, -1)
                phi, theta = unpack_params(params)
                compare_reconstruction(phi, theta, Xtrue, encode, decode, t)
                # mu0, log_sigma_diag0, W, U, b = encode(phi, Xtrue)
                # z = sample_from_pz(mu0, log_sigma_diag0, W, U, b)
                # logits = decode(theta, z)
                # Xhat = npr.binomial(1, logits)
                #
                # Xtrue_im = Xtrue.reshape(28, 28)
                # Xhat_im = Xhat.reshape(28, 28)
                #
                # plot_mnist(Xtrue_im, Xhat_im)
                # plt.savefig(figname.format(t))
                # plt.close()


    variational_params = adam(gradient, init_params, step_size=step_size, callback=callback, num_iters=max_iter)
    pbar.close()

    return unpack_params(variational_params)