// Simple test to verify API connectivity
const API_URL = 'http://localhost:8002';

async function testAPI() {
  try {
    console.log('Testing API connection to:', API_URL);
    const response = await fetch(`${API_URL}/v1/marketplace/plugins`);
    console.log('Response status:', response.status);
    const data = await response.json();
    console.log('Plugins count:', data.count);
    console.log('First plugin:', data.plugins[0]?.display_name);
    return data;
  } catch (error) {
    console.error('API Error:', error);
  }
}

testAPI();
