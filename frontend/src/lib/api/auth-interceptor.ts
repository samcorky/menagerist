import { client } from './generated/client.gen';
import { handleAuthResponse } from './auth-events';

client.interceptors.response.use(async (response, request) => {
	await handleAuthResponse(response, request.url);
	return response;
});

export default {};
