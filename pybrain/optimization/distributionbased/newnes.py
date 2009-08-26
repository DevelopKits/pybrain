from pybrain.tools.rankingfunctions import TopLinearRanking
from pybrain.optimization.distributionbased.distributionbased import DistributionBasedOptimizer

from scipy.stats import cauchy
from random import gauss, uniform
from scipy.linalg import norm, expm2, inv, det
from scipy import zeros, dot, array, exp, randn, eye, outer, diag, power, sqrt, mean, log, pi


__author__ = 'Daan Wierstra, Tom Schaul, Tobias Glasmachers'


class NES(DistributionBasedOptimizer):
    """ THE Natural Evolution Strategies algorithm. 
    New implementation (08/2009). """
    
    # distribution types
    GAUSSIAN = 1
    CAUCHY = 2
    GENERALIZEDGAUSSIAN = 3
    STUDENTT = 4    
    
    distributionType = GAUSSIAN
    
    # parameters, which can be set but have a good (adapted) default value
    learningRate = None 
    batchSize = None 
    shapingFunction = TopLinearRanking(topFraction = 0.5)

    # variations for the algorithm
    elitism = False    
    coupledDimensions = True    
    symmetricSampling = False
    importanceMixing = True
    forcedRefresh = 0.01
    
    # fixed settings
    minimize = False
    storeAllEvaluations = True
    
    
    def _additionalInit(self):
        assert not self.minimize
        assert self.storeAllEvaluations
        if self.batchSize is None:
            self.batchSize = 10*self.numParameters
        assert not (self.symmetricSampling and self.batchSize % 2 == 1)
        if self.learningRate is None:
            self.learningRate = 1.
        self._allSampled = []
        self.center = self._initEvaluable
        self.lastCenter = None
        self.transformer = eye(self.numParameters)
        self.lastTransformer = None
        self.detDiffTransformers = 1.
        
    def _produceRadius(self):
        if self.distributionType == self.GAUSSIAN:
            return gauss(0, 1) 
        elif self.distributionType == self.CAUCHY:
            return cauchy()
        else:
            raise NotImplementedError('Distribution type '+str(self.distributionType)+' not yet implemented.')        
            
    def _coordTransform(self, sample):        
        return dot(self.transformer.T, sample)+self.center
    
    def _produceSample(self):
        """ Generate a new sample, and its transformation into the current coordinate system,
        and its evaluation. """
        if self.coupledDimensions:
            direction = randn(self.numParameters)
            direction /= norm(direction)
            sample = self._produceRadius() * direction * sqrt(self.numParameters)
        else:
            sample = array([self._produceRadius() for _ in range(self.numParameters)])
        return sample
        
    def _produceSamples(self):
        """ Append batch size new samples and evaluate them. """
        if self.numLearningSteps == 0 or not self.importanceMixing:
            if self.symmetricSampling:
                for _ in range(self.batchSize/2):
                    sample = self._produceSample()
                    sym_sample = -sample
                    tsample = self._coordTransform(sample)
                    sym_tsample = self._coordTransform(sym_sample)
                    self._oneEvaluation(tsample)
                    self._oneEvaluation(sym_tsample)
                    self._allSampled.append(sample)
                    self._allSampled.append(sym_sample)                    
            else:
                for _ in range(self.batchSize):
                    sample = self._produceSample()
                    tsample = self._coordTransform(sample)
                    self._oneEvaluation(tsample)
                    self._allSampled.append(sample)
                        
        else:
            dCenter = self.center - self.lastCenter
            def oldpdf(s):
                s = dot(dA.T, s) - dCenter        
                return exp(-0.5*dot(s,s)) / self.detDiffTransformers
            def newpdf(s):
                return exp(-0.5*dot(s,s))
            oldpoints, oldfitnesses, newpoints = importanceMixing(self._allSampled[-self.batchSize:], 
                                                                  self._allEvaluations[-self.batchSize:], 
                                                                  oldpdf, newpdf, 
                                                                  self._produceSample
                                                                  )
            if self.symmetricSampling and len(oldpoints)%2 == 1:
                oldpoints.pop()
                oldfitnesses.pop()
            for sample, f in zip(oldpoints, oldfitnesses):
                self._allSampled.append(sample)
                self._allEvaluations.append(f)
                
            if self.symmetricSampling:
                for sample in newpoints[:self.batchSize-len(oldpoints)]:                
                    sym_sample = -sample
                    tsample = self.coordTransform(sample)
                    sym_tsample = self.coordTransform(sym_sample)
                    self._oneEvaluation(tsample)
                    self._oneEvaluation(sym_tsample)
                    self._allSampled.append(sample)
                    self._allSampled.append(sym_sample)    
            else:                    
                for sample in newpoints:
                    tsample = self.coordTransform(sample)
                    self._oneEvaluation(tsample)
                    self._allSampled.append(sample)
                    
    def _learnStep(self):
        self._produceSamples()
        samples = self._allSampled[-self.batchSize:]
        fits = self._allEvaluations[-self.batchSize:]
        shapedFits = self.shapingFunction(fits)
        self._updateCoordinateSystem(array(samples), shapedFits)
        
    def _updateCoordinateSystem(self, samples, fits):
        self.lastCenter = self.center
        self.lastTransformer = self.transformer
        fits /= sum(fits)
        
        # baseline
        #fits -= 1./self.batchSize
        
        # update center
        centergradient = dot(samples.T, fits)
        dCenter = self.learningRate * centergradient 
        
        # update covariance matrix
        gradientL = zeros((self.numParameters, self.numParameters))
        numGradientL = zeros((self.numParameters, self.numParameters))
        
        L = zeros((self.numParameters, self.numParameters))
        x = zeros(self.numParameters)
        def xxx(L, x, s):
            return log(1./sqrt(det(expm2(L))
                       /power(2*pi, self.numParameters)) 
                       * exp(-0.5*dot(s-x, dot(expm2(-L), (s-x)))))
            
        
        for s, fit in zip(samples, fits):
            gradientL +=  fit * (0.5 * outer(s,s) - 0.5 * eye(self.numParameters))  
            
            if True:
                for i in range(self.numParameters):
                    for j in range(i+1):
                        if i == j:
                            L[i,j] -= 5e-6 * sqrt(2)
                            v1 = xxx(L, x, s)
                            L[i,j] += 1e-5 * sqrt(2)
                            v2 = xxx(L, x, s)
                            L[i,j] -= 5e-6 * sqrt(2)                            
                            numGradientL[i,j] += fit * (v2-v1) / 1e-5
                        else:
                            L[i,j] -= 5e-6
                            L[j,i] -= 5e-6
                            v1 = xxx(L, x, s)
                            L[i,j] += 1e-5
                            L[j,i] += 1e-5
                            v2 = xxx(L, x, s)
                            L[i,j] -= 5e-6
                            L[j,i] -= 5e-6
                            numGradientL[j,i] += fit * (v2-v1) / 1e-5
                            numGradientL[i,j] += fit * (v2-v1) / 1e-5
                        #print i, j, (v2-v1) / 1e-15
        if True:
            print gradientL
            print numGradientL
            print 
            
        # MAGIC CORRECTION BASED ON BASES WITH MAGIC NUMBERS
        gradientL *= 2
        gradientL -= 0.5* diag(diag(gradientL))
        
            
        dL = self.learningRate * gradientL 
        dTransformer =  expm2(0.5 * dL)
        
        self.center = self.lastCenter + dot(self.lastTransformer.T, dCenter)   
        self.transformer = dot(dTransformer, self.lastTransformer)
        
        
        if self.numLearningSteps % 10 == 0:
            print 'sdet', power(det(self.transformer), 1./self.numParameters)
            #print 'A_new', self.transformer
            print 'Amean', mean(abs(self.transformer))
            print 'mu_new', self.center
            print
        
        
        # transform the previous samples to the new coordinate system
        for i in range(self.batchSize):        
            self._allSampled[-(i+1)] = dot(inv(dTransformer), (self._allSampled[-(i+1)] - dCenter))
        
    def _updateCenter(self, samples, fits):        
        if self.elitism:
            self.x = self.bestEvaluable
        else:
            uCenter = 0 # TODO        
            self.center += self.learningRate * uCenter            
    
    
            
def importanceMixing(oldpoints, oldfitnesses, oldpdf, newpdf, newdistr, forcedRefresh = 0.01):
    """  """
    reusepoints = []
    reusefitnesses = []
    batch = len(oldpoints)
    for sample, f in zip(oldpoints, oldfitnesses):        
        r = uniform(0, 1)
        if r < (1-forcedRefresh) * newpdf(sample) / oldpdf(sample):
            reusepoints.append(sample)
            reusefitnesses.append(f)
        # never use only old samples
        if batch - len(reusepoints) < batch * forcedRefresh:
            break
    
    newpoints = []
    # add the remaining ones
    while len(reusepoints) < len(oldpoints):
        r = uniform(0, 1)
        sample = newdistr()
        if r < forcedRefresh:
            newpoints.append(sample)
        else:
            if r < 1 - oldpdf(sample)/newpdf(sample):
                newpoints.append(sample)  
            
    return reusepoints, reusefitnesses, newpoints    
    