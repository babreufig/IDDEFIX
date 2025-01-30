#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 23 13:20:11 2020

@author: sjoly
@modified by: MaltheRaschke
"""
import numpy as np
from functools import partial
from scipy.optimize import minimize

from .solvers import Solvers
from .objectiveFunctions import ObjectiveFunctions as obj
from .resonatorFormulas import Impedances as imp
from .resonatorFormulas import Wakes as wak
from .utils import compute_fft

class EvolutionaryAlgorithm:
    def __init__(self, 
                 frequency_data, 
                 impedance_data,
                 N_resonators,
                 parameterBounds,
                 plane="longitudinal", 
                 objectiveFunction = obj.sumOfSquaredError,
                 wake_length=None,
                 time_data=None,
                 wake_data=None,
                ):
        self.frequency_data = frequency_data
        self.impedance_data = impedance_data
        self.time_data = time_data
        self.wake_data = wake_data
        self.N_resonators = N_resonators
        self.parameterBounds = parameterBounds
        self.objectiveFunction = objectiveFunction
        self.wake_length = wake_length
        self.plane = plane

        if plane == "longitudinal" and N_resonators > 1:
            self.fitFunction = partial(imp.n_Resonator_longitudinal_imp, wake_length=wake_length)
        elif plane == "transverse" and N_resonators > 1:
            self.fitFunction = partial(imp.n_Resonator_transverse_imp, wake_length=wake_length)
        elif plane == "longitudinal" and N_resonators == 1:
            self.fitFunction = partial(imp.Resonator_longitudinal_imp, wake_length=wake_length)
        elif plane == "transverse" and N_resonators == 1:
            self.fitFunction = partial(imp.Resonator_transverse_imp, wake_length=wake_length)

        self.evolutionParameters = None
        self.minimizationParameters = None
                
    def check_impedance_data(self):
        """
        Small function to avoid 0 frequency leading to zero division when using resonators.
        """
        mask = np.where(self.frequency_data > 0.)[0]
        self.frequency_data = self.frequency_data[mask]
        self.impedance_data = self.impedance_data[mask]
    

    def generate_Initial_Parameters(self, parameterBounds, objectiveFunction, fitFunction,
                                x_values_data, y_values_data,
                                maxiter=2000, popsize=150, 
                                mutation=(0.1, 0.5), crossover_rate=0.8,
                                tol=0.01,
                                solver='scipy',
                               ):    
        """
        Generates initial parameter guesses for a minimization algorithm.

        This function uses a differential evolution (DE) solver to find approximate
        solutions to a minimization problem, which can be used as initial guesses for
        more precise optimizers.

        Args:
            parameterBounds: A list of tuples representing the upper and lower bounds
                            for each parameter.
            objective_function: A function that calculates the cost given a set of
                            parameters and data. The signature should be
                            `objective_function(parameters, fit_function, x_data, y_data)`.
            fit_function: A function that calculates the fit between a model and data.
                        The signature should be `fit_function(parameters, x_data, y_data)`.
            x_values_data: The x-values of the data to fit.
            y_values_data: The y-values of the data to fit.
            maxiter: The maximum number of iterations for the DE solver.
            popsize: The population size for the DE algorithm.
            mutation: A tuple of two floats representing the mutation factors.
            crossover_rate: The crossover rate for the DE algorithm.
            tol: The tolerance for convergence.
            solver: The solver to use for differential evolution. Valid options are
                    "scipy", "pyfde", or "pyfde_jade". Defaults to "scipy".

        Returns:
            A tuple containing:
                - The estimated initial parameters found by the DE solver.
                - A message indicating the solver's status.
        """

        
        objective_function = partial(objectiveFunction, 
                                        fitFunction=fitFunction,
                                        x=x_values_data, 
                                        y=y_values_data
                                    )
        
        # Map solver names to functions
        solver_functions = {
            "scipy": Solvers.run_scipy_solver,
            "pyfde": Solvers.run_pyfde_solver,
            "pyfde_jade": Solvers.run_pyfde_jade_solver,
        }

        solver_function = solver_functions.get(solver)
        if solver == "pyfde_jade":
            mutation, crossover_rate = None, None
        
        if not solver_function:
            raise ValueError(f"Invalid solver name: {solver}")
            
        solution, message = solver_function(parameterBounds, 
                                            objective_function,
                                            maxiter=maxiter, 
                                            popsize=popsize, 
                                            mutation=mutation, 
                                            crossover_rate=crossover_rate,
                                            tol=tol)
        
        return solution, message
    
    def run_differential_evolution(self, 
                             maxiter=2000, 
                             popsize=15, 
                             mutation=(0.1, 0.5), 
                             crossover_rate=0.8, 
                             tol=0.01, 
                             #workers=-1, 
                             vectorized=False,
                             solver='scipy',
                             iteration_convergence=False, debug=False):
        evolutionParameters, warning = self.generate_Initial_Parameters(self.parameterBounds, 
                                                           self.objectiveFunction, 
                                                           self.fitFunction, 
                                                           self.frequency_data, 
                                                           self.impedance_data, 
                                                           maxiter=maxiter, 
                                                           popsize=popsize, 
                                                           mutation=mutation, 
                                                           crossover_rate=crossover_rate,
                                                           tol=tol,
                                                           solver=solver
                                                           #workers=workers, vectorized=vectorized,
                                                           #iteration_convergence=iteration_convergence
                                                                )

        self.evolutionParameters = evolutionParameters
        self.warning = warning
        self.display_resonator_parameters(self.evolutionParameters)
            
    def run_minimization_algorithm(self, margin=0.1, method='Nelder-Mead'):
        """
        Minimization algorithm is used to refine results obtained by the DE algorithm. 
        They are used as initial guess for the algorithm and each parameter is allowed to be
        increased or decreased by 100*margin [%].
        """
        print('Method for minimization : '+method)
        objective_function = partial(self.objectiveFunction, fitFunction=self.fitFunction,
                                x=self.frequency_data, y=self.impedance_data)
        
        if self.evolutionParameters is not None:
            minimizationBounds = [sorted(((1-margin)*p, (1+margin)*p)) for p in self.evolutionParameters]
            minimizationParameters = minimize(objective_function, 
                                              x0=self.evolutionParameters,
                                              bounds=minimizationBounds,
                                              tol=1, #empiric value, documentation is cryptic
                                              method=method, 
                                              options={'maxiter': self.N_resonators * 1000,
                                                       'maxfev': self.N_resonators * 1000,
                                                       'disp': False,
                                                       'adaptive': True}
                                             )
        else:
            print('Differential Evolution algorithm not run, minimization only')
            minimizationParameters = minimize(objective_function, 
                                              x0=np.mean(self.parameterBounds, axis=1),
                                              bounds=self.parameterBounds, 
                                              method=method, 
                                              tol=1,
                                              options={'maxiter': self.N_resonators * 5000,
                                                       'maxfev': self.N_resonators * 5000,
                                                       'disp': False,
                                                       'adaptive': True}
                                             ) 
        self.minimizationParameters = minimizationParameters.x
        self.display_resonator_parameters(self.minimizationParameters)
    
    def display_resonator_parameters(self, solution, to_markdown=False):
        """
        Displays resonance parameters in a formatted table using ASCII characters.

        Args:
            solution: A NumPy array of resonator parameters, typically shaped (n_resonators, 3).
        """

        n_resonators, _ = solution.reshape(-1,3).shape
        header_format = "{:^10}|{:^24}|{:^18}|{:^18}"
        data_format = "{:^10d}|{:^24.2e}|{:^18.2f}|{:^18.3e}"
        if to_markdown:
            #change format to markdown
            pass
        else:
            print("\n")
            print("-" * 70)


            # Print header
            print(header_format.format("Resonator", "Rs [Ohm/m or Ohm]", "Q", "fres [Hz]"))
            print("-" * 70)

            # Print data
            for i, parameters in enumerate(solution.reshape(-1,3)):
                print(data_format.format(i + 1, *parameters))

            print("-" * 70)

    def get_wake(self, time_data=None, pars='minimization'):

        # Check for time data 
        if time_data is None:
            if self.time_data is None:
                raise AttributeError("Provide time data array")
            time_data = self.time_data
        else:
            if self.time_data is None:
                self.time_data = time_data

        # Which pars to use
        if pars == 'minimization' and self.minimizationParameters is not None:
            pars = self.minimizationParameters
        else:
            pars = self.evolutionParameters

        # Which plane and formula
        if self.plane == "longitudinal" and self.N_resonators > 1:
            wake_data = wak.n_Resonator_longitudinal_wake(time_data, pars)
        elif self.plane == "transverse" and self.N_resonators > 1:
            wake_data = wak.n_Resonator_transverse_wake(time_data, pars)
        elif self.plane == "longitudinal" and self.N_resonators == 1:
            wake_data = wak.Resonator_longitudinal_wake(time_data, pars)
        elif self.plane == "transverse" and self.N_resonators == 1:
            wake_data = wak.Resonator_transverse_wake(time_data, pars)

        if self.wake_data is None:
            self.wake_data = wake_data

        return wake_data
    
    def get_wake_potential(self, time_data=None, sigma=1e-9, pars='minimization'):

        # Check for time data 
        if time_data is None:
            if self.time_data is None:
                raise AttributeError("Provide time data array")
            time_data = self.time_data
        else:
            if self.time_data is None:
                self.time_data = time_data

        # Which pars to use
        if pars == 'minimization' and self.minimizationParameters is not None:
            pars = self.minimizationParameters
        else:
            pars = self.evolutionParameters

        # Which plane and formula
        if self.plane == "longitudinal" and self.N_resonators > 1:
            wake_potential_data = imp.n_Resonator_longitudinal_wake_potential(time_data, sigma, pars)
        elif self.plane == "transverse" and self.N_resonators > 1:
            wake_potential_data = imp.n_Resonator_transverse_wake_potential(time_data, sigma, pars)
        elif self.plane == "longitudinal" and self.N_resonators == 1:
            wake_potential_data = imp.Resonator_longitudinal_wake_potential(time_data, sigma, pars)
        elif self.plane == "transverse" and self.N_resonators == 1:
            wake_potential_data = imp.Resonator_transverse_wake_potential(time_data, sigma, pars)

        return wake_potential_data
    
    def get_impedance_from_fitFunction(self, frequency_data=None, pars='minimization'):
        # Check for frequency data 
        if frequency_data is None:
            if self.frequency_data is None:
                raise AttributeError("Provide frequency data array")
            frequency_data = self.frequency_data
        else:
            if self.frequency_data is None:
                self.frequency_data = frequency_data

        # Which pars to use
        if pars == 'minimization' and self.minimizationParameters is not None:
            pars = self.minimizationParameters
        else:
            pars = self.evolutionParameters

        impedance_data = self.fitFunction(frequency_data, pars)
        return 

    def get_impedance(self, frequency_data=None,
                      pars='minimization', wakelength=None):
        # Check for frequency data 
        if frequency_data is None:
            if self.frequency_data is None:
                raise AttributeError("Provide frequency data array")
            frequency_data = self.frequency_data
        else:
            if self.frequency_data is None:
                self.frequency_data = frequency_data

        # Which pars to use
        if pars == 'minimization' and self.minimizationParameters is not None:
            pars = self.minimizationParameters
        else:
            pars = self.evolutionParameters

        # Which plane and formula
        if self.plane == "longitudinal" and self.N_resonators > 1:
            impedance_data = wak.n_Resonator_longitudinal_imp(frequency_data, pars, wakelength)
        elif self.plane == "transverse" and self.N_resonators > 1:
            impedance_data = wak.n_Resonator_transverse_imp(frequency_data, pars, wakelength)
        elif self.plane == "longitudinal" and self.N_resonators == 1:
            impedance_data = wak.Resonator_longitudinal_imp(frequency_data, pars, wakelength)
        elif self.plane == "transverse" and self.N_resonators == 1:
            impedance_data = wak.Resonator_transverse_imp(frequency_data, pars, wakelength)
        return 
    
    def get_impedance_from_fft(self, time_data=None, wake_data=None, 
                               fmax=3e9, samples=1001):
        # Check for time data 
        if time_data is None:
            if self.time_data is None:
                raise AttributeError("Provide time data array")
            time_data = self.time_data
        else:
            if self.time_data is None:
                self.time_data = time_data
        
        wake_data = self.get_wake(self.time_data)

        f, Z = compute_fft(data_time=time_data,
                           data_wake=wake_data,
                           fmax=fmax, 
                           samples=samples)
        
        if self.plane is 'transverse':
            Z *= -1j
        
        return f, Z

    def compute_fft(self, data_time=None, data_wake=None, fmax=3e9, samples=1001):
        # Check for time data - not override self
        if time_data is None:
            if self.time_data is None:
                raise AttributeError("Provide time data array")
            time_data = self.time_data

        # Check for wake data - not override self
        if wake_data is None:
            if self.wake_data is None:
                raise AttributeError("Provide wake data array")
            wake_data = self.wake_data

        compute_fft(data_time, data_wake, fmax, samples)

    def get_extrapolated_wake(self, new_end_time, dt=0.01, 
                              time_data=None, pars='minimization'):

        # Check for time data 
        if time_data is None:
            if self.time_data is None:
                raise AttributeError("Provide time data array")
            time_data = self.time_data
        else:
            if self.time_data is None:
                self.time_data = time_data

        dt = np.min(time_data[1:]-time_data[:-1])

        ext_time_data = np.concatenate(time_data[:-1], 
                                       np.arange(time_data[-1], new_end_time, dt))
        
        ext_wake_data = self.get_wake(ext_time_data, pars=pars)

        return ext_time_data, ext_wake_data   
    