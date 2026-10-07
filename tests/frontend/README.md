# Optional browser-logic test
Loads the real page and real `static/js/tutor.js` in a simulated browser (jsdom) and drives the whole flow
(consent, language, record, answer, rating) against a RUNNING server. Needs Node.js 18+.

    # terminal 1: python -m scripts.mock_gateway
    # terminal 2: DASHBOARD_KEY=k python run.py          (any port: set BASE_URL below)
    cd tests/frontend && npm install && BASE_URL=http://127.0.0.1:5000 DASHBOARD_KEY=k node fe_test.js

Use only against a LOCAL server with the mock gateway: it creates a test interaction in that database.
