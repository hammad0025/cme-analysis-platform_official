export const IS_PRODUCTION_BUILD = process.env.NODE_ENV === 'production';

export const DEV_MODE = process.env.REACT_APP_DEV_MODE === 'true' && !IS_PRODUCTION_BUILD;

export const API_BASE_URL =
  process.env.REACT_APP_API_URL ||
  'https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod';

export const ALLOW_PRODUCTION_MOCK_API =
  process.env.REACT_APP_ALLOW_PRODUCTION_MOCK_API === 'true';

export const CAN_USE_MOCK_API = !IS_PRODUCTION_BUILD || ALLOW_PRODUCTION_MOCK_API;

export const USE_MOCK_API = (() => {
  const explicit = process.env.REACT_APP_USE_MOCK_API;
  const apiUrl = (process.env.REACT_APP_API_URL || '').trim();

  if (!CAN_USE_MOCK_API) return false;
  if (explicit === 'true') return true;
  if (explicit === 'false') return false;

  return DEV_MODE && !apiUrl;
})();
