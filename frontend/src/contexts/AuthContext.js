import React, { createContext, useContext, useState, useEffect } from 'react';
import { CognitoUserPool, CognitoUser, AuthenticationDetails } from 'amazon-cognito-identity-js';
import { DEV_MODE } from '../config/runtime';

const AuthContext = createContext();

const DEV_USER = {
  email: 'demo@cme.local',
  given_name: 'Demo',
  family_name: 'Reviewer',
  username: 'demo',
};

const userPool = new CognitoUserPool({
  UserPoolId: process.env.REACT_APP_USER_POOL_ID || 'us-east-1_t8m33Ihhq',
  ClientId: process.env.REACT_APP_USER_POOL_WEB_CLIENT_ID || '42e444v111efsa21b6b3v09svp',
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (DEV_MODE) {
      setUser(DEV_USER);
      localStorage.setItem('auth_token', 'dev-mode-token');
      setLoading(false);
      return;
    }
    checkUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkUser = () => {
    const clearSession = () => {
      localStorage.removeItem('auth_token');
      setUser(null);
      setLoading(false);
    };

    const cognitoUser = userPool.getCurrentUser();
    if (cognitoUser) {
      cognitoUser.getSession((err, session) => {
        if (err) {
          clearSession();
          return;
        }
        if (session.isValid()) {
          localStorage.setItem('auth_token', session.getIdToken().getJwtToken());
          cognitoUser.getUserAttributes((err, attributes) => {
            if (err) {
              clearSession();
              return;
            }
            const userData = {};
            attributes.forEach((attr) => {
              userData[attr.Name] = attr.Value;
            });
            setUser({ ...userData, username: cognitoUser.getUsername() });
            setLoading(false);
          });
        } else {
          clearSession();
        }
      });
    } else {
      clearSession();
    }
  };

  const login = (username, password) => {
    if (DEV_MODE) {
      setUser(DEV_USER);
      localStorage.setItem('auth_token', 'dev-mode-token');
      return Promise.resolve({ devMode: true });
    }
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({
        Username: username,
        Pool: userPool,
      });

      const authDetails = new AuthenticationDetails({
        Username: username,
        Password: password,
      });

      cognitoUser.authenticateUser(authDetails, {
        onSuccess: (session) => {
          cognitoUser.getUserAttributes((err, attributes) => {
            if (err) {
              reject(err);
              return;
            }
            const userData = {};
            attributes.forEach((attr) => {
              userData[attr.Name] = attr.Value;
            });
            setUser({ ...userData, username: cognitoUser.getUsername() });
            
            // Store token for API calls
            localStorage.setItem('auth_token', session.getIdToken().getJwtToken());
            resolve(session);
          });
        },
        onFailure: (err) => {
          reject(err);
        },
        newPasswordRequired: (userAttributes, requiredAttributes) => {
          // Auto-complete password reset with same password if user status requires it
          cognitoUser.completeNewPasswordChallenge(
            authDetails.Password,
            requiredAttributes,
            {
              onSuccess: (session) => {
                cognitoUser.getUserAttributes((err, attributes) => {
                  if (err) {
                    reject(err);
                    return;
                  }
                  const userData = {};
                  attributes.forEach((attr) => {
                    userData[attr.Name] = attr.Value;
                  });
                  setUser({ ...userData, username: cognitoUser.getUsername() });
                  localStorage.setItem('auth_token', session.getIdToken().getJwtToken());
                  resolve(session);
                });
              },
              onFailure: (err) => {
                reject({ code: 'PasswordResetRequiredException', message: err.message || 'Password reset required' });
              }
            }
          );
        },
      });
    });
  };

  const logout = () => {
    if (!DEV_MODE) {
      const cognitoUser = userPool.getCurrentUser();
      if (cognitoUser) {
        cognitoUser.signOut();
      }
    }
    localStorage.removeItem('auth_token');
    setUser(null);
  };

  const changePassword = (oldPassword, newPassword) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = userPool.getCurrentUser();
      if (!cognitoUser) {
        reject(new Error('No user logged in'));
        return;
      }

      cognitoUser.getSession((err, session) => {
        if (err) {
          reject(err);
          return;
        }

        cognitoUser.changePassword(oldPassword, newPassword, (err, result) => {
          if (err) {
            reject(err);
            return;
          }
          resolve(result);
        });
      });
    });
  };

  const value = {
    user,
    loading,
    login,
    logout,
    changePassword,
    isAuthenticated: !!user,
    devMode: DEV_MODE,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
