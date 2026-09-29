from fastapi.testclient import TestClient
from app.main import app


def main():
    with TestClient(app) as c:
        assert c.get('/health').status_code == 200
        r = c.post('/api/auth/register', json={
            'organization_name': 'Smoke Test',
            'site_url': 'https://example.invalid',
            'name': 'Tester',
            'email': 'smoke@example.local',
            'password': 'secret12',
        })
        assert r.status_code in (200, 409), r.text
        if r.status_code == 409:
            assert c.post('/api/auth/login', json={'email':'smoke@example.local','password':'secret12'}).status_code == 200
        profiles = c.get('/api/v1/search-profiles').json()
        assert profiles
        assert c.post(f"/api/v1/search-profiles/{profiles[0]['id']}/run").status_code == 200
        opportunities = c.get('/api/v1/opportunities').json()
        assert isinstance(opportunities, list)
        assert c.get('/api/v1/export.xlsx').status_code == 200
        print('LeadRadar MVP smoke test: OK')


if __name__ == '__main__':
    main()
