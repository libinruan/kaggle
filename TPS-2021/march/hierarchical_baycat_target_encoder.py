#%% Target Encoder Package Experiment

# ------------------------------- Experiment 1 ------------------------------- #

import pandas as pd
from category_encoders import TargetEncoder
from sklearn.model_selection import KFold
from sklearn.preprocessing import FunctionTransformer
from sklearn.pipeline import Pipeline
a = ['a', 'a', 'a', 'b', 'a', 'b', 'a', 'b', 'b', 'b']
b = [0, 1, 0, 0, 1, 0, 0, 0, 0, 1]
data = pd.DataFrame({'feature': a, 'label': b})
labels = data.label
kf = KFold(n_splits=5, shuffle=False)
for train_idx, test_idx in kf.split(data):
    print(train_idx, test_idx)
    te = TargetEncoder(cols='feature').fit(data.iloc[train_idx], labels[train_idx])
    to = te.transform(data.iloc[test_idx])
    print(to)
# screenshot: https://i.postimg.cc/kMNxwzqg/2021-03-22-at-09-09-39.png

# %% FunctionTransformer on Pandas Column Multiplication Experiment
# functiontransformer is used for Column Manipuplation.

# ------------------------------- Experiment 2 ------------------------------- #

import random
def generate_num_interaction(X):
    cols = X.columns
    for i in range(len(cols)-1):
        for j in range(i+1, len(cols)):
            colname = cols[i] + '_' + cols[j]
            X[colname] = X[cols[i]] * X[cols[j]]
    return X
n1 = [1, 2, 3]
n2 = [4, 5, 6]
n3 = random.choices(range(7,10), k=3)
data = pd.DataFrame({'n1':n1, 'n2':n2, 'n3':n3}, index=['o','p','q'])
pipeline = Pipeline([
    ('test', FunctionTransformer(
        func=generate_num_interaction
    ))
])
pipeline.fit_transform(data)
# screenshot: https://i.postimg.cc/dtm5fncJ/2021-03-22-at-09-13-25.png


# %%

# ------------------------------- Experiment 3 ------------------------------- #
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from collections import defaultdict
from sklearn.model_selection import KFold

# class GetHierarchicalSubsets():
#     """
#     >>> groups = ['n1.n2.n4', 'n3.n4', 'n2']
#     >>> test = GetHierarchicalSubsets(groups)
#     >>> test.generate_subsets()
#     [['n1'], ['n3'], ['n2'], ['n1', 'n2'], ['n3', 'n4'], ['n1', 'n2', 'n4']]
#     """
#     def __init__(self, groups, delimiter='.'):
#         self.cnt = 0 
#         self.groups = groups
#         self.delimiter = delimiter
#         self.subsets = defaultdict(list)
#     def generate_subsets(self):
#         for g in self.groups:
#             chain = g.split(self.delimiter)
#             for i in range(len(chain)):
#                 if chain[i]: self.subsets[i].append(chain[:i+1])
#         ret = []
#         for _, v in self.subsets.items():
#             ret.extend(v)
#         return ret            

class HierarchicalBetaTargetEncoder(BaseEstimator, TransformerMixin):
    def __init__(self, 
                 group_cols, 
                 target_col='target', 
                 N_min=1, 
                 drop_original=False, 
                 CV=True, 
                 n_fold=5,
                 drop_intermediate=False,
                 delimiter='.'):
        self.group_cols = group_cols # List of column names combination: e.g. ['n1.n2.n4', 'n3.n4', 'n2'].
        self.target_col = target_col # String: 'target' by default.
        self.stats = defaultdict(dict) # key: column names combination; value: corresponding info about n, N, and computed code.
        self.N_min = N_min # regularization control
        self.drop_original = drop_original # toggle key for whether to drop original column name(s) or not.
        self.CV = CV # Bool: 
        self.n_fold = n_fold
        self.delimiter = delimiter
        self.drop_intermediate = drop_intermediate
        self.set_original_col = [] 

    def fit(self, X, y):
        # self.col_subsets = GetHierarchicalSubsets(self.group_cols).generate_subsets()
        
        self.col_subsets = self._generate_subsets(self.group_cols)
        df = pd.concat([X, y], axis=1)
        assert(isinstance(self.target_col, str))
        df.columns = X.columns.tolist() + [self.target_col] 
        assert(self._check_col_consistency(X))
        if not self.CV:
            self._single_fit(df)
        else:
            self._cv_fit(df)
        return self

    def _single_fit(self, df):
        for subset in self.col_subsets:
            df_stat, stat, cross_features = self._update(df, subset)
            features_encoded = cross_features + '_code'
            self.stats[cross_features] = pd.merge(
                stat, 
                df_stat.groupby(subset)[features_encoded].mean(), 
                left_index=True, 
                right_index=True)       
        return self 

    def _cv_fit(self, df):
        kf = KFold(n_splits = self.n_fold, 
                   shuffle = False, 
                   random_state=2019)
        for subset in self.col_subsets:
            for i, (tr_idx, val_idx) in enumerate(kf.split(df)):
                df_tr, df_val = df.iloc[tr_idx], df.iloc[val_idx] # <-------------------- we should add copy() to avoid FutureWarning message.
                df_stat, stat, cross_features = self._update(df_tr, subset)
                features_encoded = cross_features + '_code'
                df.loc[df.index[val_idx], features_encoded] = pd.merge(
                        df_val[subset], 
                        df_stat.groupby(subset)[features_encoded].mean(),
                        left_on=subset,
                        right_index=True,
                        how='left'
                    )[features_encoded] \
                    .fillna(df[self.target_col].mean())  
            self.stats[cross_features] = df.groupby(subset)[features_encoded].mean().to_frame()
        return self        

    def _update(self, df, subset):
        if len(subset) == 1:
            self.set_original_col.append(*subset)
            upper_level_cols = 'global'
            if not upper_level_cols + '_prior_mean' in df.columns:
                df[upper_level_cols + '_prior_mean'] = df[self.target_col].mean()
        else:
            upper_level_cols = self.delimiter.join(subset[:-1]) # e.g. the n1.n2 subset's upper level feature is `n1`.
            if not upper_level_cols + '_prior_mean' in df.columns: 
                df[upper_level_cols + '_prior_mean'] = pd.merge(
                        df[subset[:-1]], 
                        self.stats[upper_level_cols][upper_level_cols + '_code'], 
                        left_on=subset[:-1], 
                        right_index=True, 
                        how='left'
                    )[upper_level_cols + '_code']
        
        stat = df.groupby(subset).agg(
            n=(self.target_col, 'sum'),
            N=(self.target_col, 'count'),
            prior_mean=(upper_level_cols + '_prior_mean', 'mean')
        )
        # Calculate posterior mean
        df_stat = pd.merge(df[subset], stat, left_on=subset, right_index=True, how='left')
        df_stat['n'].mask(df_stat['n'].isnull(), df_stat['prior_mean'], inplace=True) 
        df_stat['N'].fillna(1., inplace=True)
        df_stat['N_prior'] = df_stat['N'].map(lambda x: max(self.N_min - x, 0))
        df_stat['alpha_prior'] = df_stat['prior_mean'] * df_stat['N_prior']
        df_stat['beta_prior'] = (1. - df_stat['prior_mean']) * df_stat['N_prior'] # Large N -> zero N_prior -> zero alpha_prior and zero beta_prior -> if n is zero as well -> alpha prior, beta prior both zero -> alpha zero -> posterior mean = zero as well.           
        if len(subset) == 1:
            cross_features = subset[0]
        else:
            cross_features = self.delimiter.join(subset)
        df_stat[cross_features + '_code'] = df_stat.apply(self._stat_mean, axis=1) # core # TEST set!!
        return df_stat, stat, cross_features

    def _generate_subsets(self, groups, delimiter='.'):
        # cnt = 0 
        # groups = groups
        # delimiter = delimiter
        subsets = defaultdict(list)    
        for g in groups:
            chain = g.split(delimiter)
            for i in range(len(chain)):
                if chain[i] and not chain[:i+1] in subsets[i]: subsets[i].append(chain[:i+1])
        ret = []
        for _, v in subsets.items():
            if not v in ret: ret.extend(v)
        return ret        

    def _stat_mean(self, df):
        alpha = df['alpha_prior'] + df['n']
        beta = df['beta_prior'] + df['N'] - df['n']
        return alpha / (alpha + beta)

    def _check_col_consistency(self, df): 
        """Check whether columns specified in `self.group_cols` are all included in `df`.
        """        
        s = set()
        for col_subset in self.col_subsets:
            s |= set(col_subset)
        for col in s:
            if not col in df.columns: return False
        return True

    def transform(self, X):
        assert(self._check_col_consistency(X))
        for subset in self.col_subsets:
            key = '.'.join(subset)
            X = pd.merge(
                    X, 
                    self.stats[key][key + '_code'], 
                    left_on=subset, 
                    right_index=True, 
                    how='left')
        if self.drop_original:
            for col in self.set_original_col:
                X.drop(col, axis=1, inplace=True)
                X.rename(columns={col+'_code': col}, inplace=True)
        if self.drop_intermediate: 
            for col in X.columns:
                if col.endswith('_code') and not col.strip('_code') in self.group_cols:
                    X.drop(col, axis=1, inplace=True)
        return X

if __name__ == '__main__':
    np.random.seed(1)
    k = 8
    n1 = np.random.choice(['a','b'], k)
    n2 = np.random.choice(['c','d'], k)
    n3 = np.random.choice(['e','f'], k)
    target = np.random.randint(0, 2, size=k)
    train = pd.DataFrame(
        {'n1': n1, 'n2': n2, 'n3':n3, 'target': target}, 
        columns=['n1', 'n2', 'n3', 'target']
    )
    train.columns = ['n1','n2','n3', 'target']
    
    display(train)

    k = 6
    n4 = np.random.choice(['a','b'], k)
    n5 = np.random.choice(['c','d'], k)
    n6 = np.random.choice(['e','f'], k)
    test = pd.DataFrame({'n4': n4, 'n2': n5, 'n3':n6})
    test.columns = ['n1','n2','n3']
    
    display(test)
    
    te = HierarchicalBetaTargetEncoder(
            ['n1.n2.n3', 'n2.n3', 'n3'], 
            target_col='target', 
            drop_original=False, 
            drop_intermediate=True,
            CV=True, 
            n_fold=2
        ) \
        .fit(train.drop('target', axis=1), train.target) \
        .transform(test)
    te
# %% Test experiment

