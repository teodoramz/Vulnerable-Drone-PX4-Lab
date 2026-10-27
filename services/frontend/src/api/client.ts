import axios from "axios";

const api = axios.create({ baseURL: "/" });

let bearer: string | null = null;

export function setToken(token: string | null): void {
  bearer = token;
}

api.interceptors.request.use((config) => {
  if (bearer) {
    config.headers.Authorization = `Bearer ${bearer}`;
  }
  return config;
});

export default api;
