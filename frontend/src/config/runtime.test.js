describe('runtime configuration', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...ORIGINAL_ENV };
    delete process.env.REACT_APP_DEV_MODE;
    delete process.env.REACT_APP_USE_MOCK_API;
    delete process.env.REACT_APP_ALLOW_PRODUCTION_MOCK_API;
    delete process.env.REACT_APP_API_URL;
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  it('blocks accidental dev and mock modes in production builds', () => {
    process.env.NODE_ENV = 'production';
    process.env.REACT_APP_DEV_MODE = 'true';
    process.env.REACT_APP_USE_MOCK_API = 'true';

    const runtime = require('./runtime');

    expect(runtime.DEV_MODE).toBe(false);
    expect(runtime.USE_MOCK_API).toBe(false);
  });

  it('allows explicit local mock mode outside production', () => {
    process.env.NODE_ENV = 'development';
    process.env.REACT_APP_USE_MOCK_API = 'true';

    const runtime = require('./runtime');

    expect(runtime.USE_MOCK_API).toBe(true);
  });

  it('allows local dev mode to default to mock when no API URL is configured', () => {
    process.env.NODE_ENV = 'development';
    process.env.REACT_APP_DEV_MODE = 'true';

    const runtime = require('./runtime');

    expect(runtime.DEV_MODE).toBe(true);
    expect(runtime.USE_MOCK_API).toBe(true);
  });
});
