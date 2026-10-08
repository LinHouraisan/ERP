let csrfToken = '';
export function setCsrfToken(value: string) { csrfToken = value; }

export async function api<T>(path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken, ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => { throw new Error('连接中断，请稍后刷新；若已提交办理，请先刷新受理记录并按原号核对。'); });
  let data;
  try { data = await response.json(); }
  catch { throw new Error('服务未返回有效结果，请稍后刷新并核对业务记录。'); }
  if (!response.ok) throw new Error(data.message || '请求失败，请稍后再试');
  return data as T;
}
