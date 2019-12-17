from tqdm import tqdm

from autograd import numpy as np
from autograd.numpy import random as npr
from autograd import grad
from autograd.misc.optimizers import adam, rmsprop
import matplotlib.pyplot as plt

from .flows import planar_flow
from .distributions import sample_from_pz, make_samples_z
from .plotting import plot_samples, plot_obs_latent
from .nn_models import nn
from .config import figname
from .utils import clear_figs, get_samples_from_params
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


def optimize(logp, X, Z_true, D, K, N, init_params, unpack_params, max_iter, step_size, verbose=True):
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

    def logdet_jac(w, z, b):
        return np.outer(w.T, hprime(np.matmul(w, z) + b))

    def F(z0, phi, theta, t):
        eps = 1e-7
        mu0, log_sigma_diag0, W, U, B = phi
        cooling_max = np.min(np.array([max_iter / 2, 10000]))
        beta_t = np.min(np.array([1, 0.001 + t / cooling_max]))

        sd = np.sqrt(np.exp(log_sigma_diag0))
        zk = z0 * sd + mu0

        running_sum = 0.
        for k in range(K):
            w, u, b = W[k], U[k], B[k]
            #TODO: Get these two work with flow params in the shape (K, N, D)
            running_sum = running_sum + np.log(eps + np.abs(1 + np.dot(u, logdet_jac(w, zk.T, b))))
            zk = planar_flow(zk, w, u, b)

        # Unsure if this should be z0 or z1 (after adding back in mean and sd)
        first = np.mean(logq0(z0))
        second = np.mean(logp(X, zk, theta))
        # second = np.mean(logp(X, zk, theta)) * beta_t  # Play with temperature
        third = np.mean(running_sum)

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
                phi, theta = unpack_params(params)
                Xhat, ZK = get_samples_from_params(phi, theta, X, K)
                plot_obs_latent(X, Z_true, Xhat, ZK)
                plt.savefig(figname.format(t))
                plt.close()

    variational_params = adam(gradient, init_params, step_size=step_size, callback=callback, num_iters=max_iter)
    pbar.close()

    return unpack_params(variational_params)
