"""
Going deep into the MNIST dataset
"""
import autograd.numpy as np
import autograd.numpy.random as npr
from mlxtend.data import loadlocal_mnist

from normflows import (config, utils, optimization,
                       distributions, nn_models, transformations)


K = 3
dim_z = 32
dim_x = 28 * 28
width = 64

encoder_architecture = {
    'width': 64,
    'hidden_layers': 2,
    'input_dim': dim_x,
    'output_dim': 2 * dim_z + 2 * dim_z * K + 1 * K,
    'activation_fn_type': 'tanh',
    'activation_fn_params': '',
    'activation_fn': np.tanh
}
decoder_architecture = {
    'width': 64,
    'hidden_layers': 2,
    'input_dim': dim_z,
    'output_dim': dim_x,
    'activation_fn_type': 'tanh',
    'activation_fn_params': '',
    'activation_fn': np.tanh,
    'output_activation_fn': transformations.sigmoid
}


encoder = nn_models.Feedforward(architecture=encoder_architecture)
decoder = nn_models.Feedforward(architecture=decoder_architecture)


def load_data():
    X, y = loadlocal_mnist(
        images_path=str(config.mnist / 'train-images-idx3-ubyte'),
        labels_path=str(config.mnist / 'train-labels-idx1-ubyte'))

    keep_digits = np.isin(y, [1, 4])
    X = X[keep_digits]
    y = y[keep_digits]
    X = X / 255
    X = (X >= 0.5).astype(int)  # Binarizing
    return X, y


def make_unpack_params():
    """Make parameter unpacking functions (this is where the NN is called)
    """
    def encode(weights, X):
        N = X.shape[0]
        phi = encoder.forward(weights.reshape(1, -1), X.T)[0]
        mu0 = phi[:dim_z].reshape(N, dim_z)
        log_sigma_diag0 = phi[dim_z:2 * dim_z].reshape(N, dim_z)
        W = phi[2 * dim_z:2 * dim_z + K * dim_z].reshape(K, N, dim_z)
        U = phi[2 * dim_z + K * dim_z:2 * dim_z + 2 * K * dim_z].reshape(K, N, dim_z)
        b = phi[-K:].reshape(K, N)

        return mu0, log_sigma_diag0, W, U, b

    def decode(weights, Z):
        logits = decoder.forward(weights.reshape(1, -1), Z.T)[0]
        return logits.T

    def unpack_params(params):
        phi = params[:encoder.D]
        theta = params[encoder.D:]
        return phi, theta

    return unpack_params, encode, decode


def get_init_params():
    init_weights = np.random.randn(encoder.D + decoder.D) * 0.1

    return init_weights


def logp(X, Z, logits):
    """Joint likelihood for MNIST

    :param X: np.ndarray -- Data (N, dim_x)
    :param Z: np.ndarray -- Latent variables (N, dim_z)
    :param logits: np.ndarray -- logits for bernoulli distribution (N, dim_x)
    :return: np.ndarray -- Log-joint probability assuming p(z) is a unit Gaussian
    """
    log_prob_z = distributions.log_std_norm(Z)
    log_prob_x = distributions.log_bern_mult(X, logits)
    return log_prob_x + log_prob_z


def run_optimization(X, init_params, unpack_params, encode, decode,
                     max_iter=20000, N=None, step_size=1e-4):
    if not N:
        N = X.shape[0]
    else:
        idx = np.random.randint(X.shape[0], size=N)
        X = X[idx]
    return optimization.optimize(logp, X, dim_z, K, N,
                                 init_params, unpack_params, encode, decode,
                                 max_iter, step_size,
                                 verbose=True)


def main():
    X, y = load_data()
    unpack_params, encode, decode = make_unpack_params()
    init_params = get_init_params()

    phi, theta = run_optimization(X, init_params, unpack_params, encode, decode,
                                  max_iter=5000, N=1000, step_size=1e-3)

    print("DONE")

if __name__ == '__main__':
    main()