from autograd import grad
from autograd.misc.optimizers import adam, rmsprop, sgd
from autograd import numpy as np
import autograd.numpy.random as npr
from autograd import scipy as sp

from tqdm import tqdm_notebook as tqdm

import matplotlib.pyplot as plt

from normflows import flows


dim_z = 1
num_samples = 10000
K = 1
rs = npr.RandomState(0)

# Defining the true flow
w_test = np.array([[-5.]])
u_test = np.array([[-2.]])
b_test = np.array([0])


def sample_from_pz(num_samples):
    Z = np.zeros((K, num_samples, dim_z))
    z = rs.randn(num_samples, dim_z)

    Z[0] = z
    Z[1] = flows.planar_flow(z, w_test[0], u_test[0], b_test[0])
    return Z


def plot_samples(Z):
    fig, axs = plt.subplots(1, 2)
    for i in range(2):
        axs[i].scatter(Z[i, :, 0], Z[i, :, 1], alpha=0.3)

    plt.show()


def gradient_create(logq0, logp, hprime, logdet_jac, F, dim_z, num_samples, K):
    def unpack_params(params):

        mu0 = params[:dim_z]
        log_sigma_diag0 = params[dim_z:2 * dim_z]
        W = params[2 * dim_z:2 * dim_z + K * dim_z].reshape(K, dim_z)
        U = params[2 * dim_z + K * dim_z:2 * dim_z + 2 * K * dim_z].reshape(K, dim_z)
        b = params[-K:]
        return mu0, log_sigma_diag0, W, U, b

    def variational_objective(params, t):
        mu0, log_sigma_diag0, W, U, b = unpack_params(params)
        z0 = rs.randn(num_samples, dim_z) * np.sqrt(np.exp(log_sigma_diag0)) + mu0
        free_energy = F(z0, mu0, log_sigma_diag0, W, U, b, logq0, dim_z, num_samples, K, t)
        return -free_energy

    gradient = grad(variational_objective)

    return variational_objective, gradient, unpack_params


def optimize(dim_z, num_samples, K, max_iter, step_size, verbose):

    def logp(z):
        first = logq0(z)
        second = np.log(np.abs(1 + np.dot(u_test, logdet_jac(w_test, z, b_test))))

        return first - second

    def logq0(z):
        '''Start with a standard Gaussian
        '''
        D = z.shape[0]
        return -D / 2 * np.log(2 * np.pi) - 0.5 * np.sum(z ** 2, axis=0)

    def hprime(x):
        return 1 - np.tanh(x) ** 2

    # Confirm this is correct
    def logdet_jac(w, z, b):
        return np.outer(w.T, hprime(np.matmul(w, z) + b))

    def m(x):
        return -1 + np.log(1 + np.exp(x))

    def F(z0, mu0, log_sigma_diag0, W, U, b, logq0, dim_z, num_samples, K, t):

        # Transforming z0 into zK
        zk = z0
        running_sum = 0
        for k in range(K):
            running_sum += np.log(1 + np.dot(U[k], logdet_jac(W[k], zk.T, b[k])))
            zk = flows.planar_flow(zk, W[k], U[k], b[k])

        return np.mean(logq0(z0)) - \
            np.mean(logp(zk.T)) - \
            np.mean(running_sum)

    objective, gradient, unpack_params = gradient_create(logq0,
                                                         logp,
                                                         hprime,
                                                         logdet_jac,
                                                         F,
                                                         dim_z,
                                                         num_samples,
                                                         K)

    pbar = tqdm(total=max_iter)

    def callback(params, t, g):
        pbar.update()
        # if verbose:
        #     if t % 1000 == 0:
        #         print(f"Iteration {t}; gradient mag: {np.linalg.norm(gradient(params, t))}")

    # Initializing
    init_mu0 = np.zeros(dim_z)
    init_log_sigma0 = np.zeros(dim_z)
    # init_W = np.ones((K, dim_z))
    # init_U = np.ones((K, dim_z))
    init_W = np.array([[-2., 0.]])
    init_U = np.array([[-2., 0.]])
    init_b = np.zeros(K)

    init_params = np.concatenate((init_mu0, init_log_sigma0, init_W.flatten(), init_U.flatten(), init_b))

    variational_params = adam(gradient, init_params, step_size=step_size, num_iters=max_iter, callback=callback)

    pbar.close()
    return unpack_params(variational_params)


def run_optimization():
    return optimize(dim_z, num_samples, K, 5000, 1e-3, True)


if __name__ == '__main__':
    plot_samples(sample_from_pz(num_samples))

