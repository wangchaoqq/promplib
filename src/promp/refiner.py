from bbolib.bbo.cost_function import CostFunction
from bbolib.bbo.distribution_gaussian import DistributionGaussian
from bbolib.bbo.updater import UpdaterCovarDecay
from bbolib.bbo.run_optimization import runOptimization
import numpy as np


class RefiningCostFunction(CostFunction):
    """ CostFunction in which the distance to the goal and the task-space (or joint-space) jerk must be minimized."""
    def __init__(self, fk, goal, mean, cov, num_basis, Gn, cost_factors=[]):
        self.goal = goal
        self.cost_factors = cost_factors
        self.Gn = Gn
        self.fk = fk
        self.num_joints = len(self.fk.joints)
        self.num_basis = num_basis
        self.mean = mean
        self.cov = cov

    def weights_to_trajectories(self, sample):
        trajectory = []
        for joint in range(self.num_joints):
            trajectory.append(np.dot(self.Gn, sample[joint * self.num_basis:(joint + 1) * self.num_basis]))
        return np.array(trajectory).T

    def cost_precision(self, last_fk):
        return np.linalg.norm(np.array(self.goal[0]) - np.array(last_fk[0]))

    def cost_orientation(self, last_fk):
        return 1 - np.dot(self.goal[1], last_fk[1]) ** 2

    def cost_joint_jerk(self, trajectory):
        trajectory_t = trajectory.T
        jerk = [np.absolute(np.diff(np.diff(np.diff(joint)))) for joint in trajectory_t]
        return np.sum(jerk)

    def cost_cartesian_jerk(self, trajectory):
        cartesian_traj = np.array([self.fk.get(point)[0] for point in trajectory]).T
        jerk = [np.absolute(np.diff(np.diff(np.diff(point)))) for point in cartesian_traj]
        return np.sum(jerk)

    def cost_likelihood(self, sample):
        # we remove the constant values from the cost and use -log of likelihood
        mean_diff = sample - self.mean
        return abs(np.dot(mean_diff.T, np.linalg.solve(self.cov, mean_diff)))

    def evaluate(self, sample):
        # Compute distance from sample to point
        trajectory = self.weights_to_trajectories(sample)
        last_fk = self.fk.get(trajectory[-1])
        cost_jerk = self.cost_joint_jerk(trajectory)
        cost_precision = self.cost_precision(last_fk)
        cost_orientation = self.cost_orientation(last_fk)
        cost_likelihood = self.cost_likelihood(sample)
        cost = self.cost_factors[0] * cost_likelihood + self.cost_factors[1] * cost_precision + self.cost_factors[2] * cost_orientation + self.cost_factors[3] * cost_jerk

        return cost, cost_likelihood, cost_precision, cost_jerk


class TrajectoryRefiner(object):
    def __init__(self, fk, num_basis, Gn, factor_likelihood=1e-7, factor_precision=1, factor_orientation=0.,
                 factor_jerk=0.2, n_samples_per_update=20, n_updates=100):
        self.fk = fk
        self.num_basis = num_basis
        self.Gn = Gn
        self.cost_factors = [factor_likelihood, factor_precision, factor_orientation, factor_jerk]
        self.n_samples_per_update = n_samples_per_update
        self.n_updates = n_updates

    def refine_trajectory(self, mean, cov, goal):
        """
        Refine a trajectory to reach goal more precisely from the given input trajectory
        :param mean: Mean of weights of the input trajectory
        :param cov: Covariance of the input trajectory
        :param goal: [[x, y, z], [x, y, z, w]]
        :return: the refined mean of weights
        """
        distribution = DistributionGaussian(mean, cov)

        eliteness = 10
        weighting_method = 'PI-BB'
        covar_decay_factor = 0.99
        updater = UpdaterCovarDecay(eliteness, weighting_method, covar_decay_factor)
        self.cost_function = RefiningCostFunction(self.fk, goal, mean, cov, self.num_basis, self.Gn, self.cost_factors)

        #import matplotlib.pyplot as plt
        #fig = plt.figure(1, figsize=(15, 5))

        mean, cov = runOptimization(self.cost_function, distribution, updater,
                                    self.n_updates, self.n_samples_per_update) #,fig, '/tmp/freek')
        #plt.savefig('/tmp/pouet' + '.svg', dpi=100, transparent=False)
        return mean
