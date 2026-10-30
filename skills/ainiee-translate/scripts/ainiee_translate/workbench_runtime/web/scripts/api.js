const key = new URL(location.href).searchParams.get("key");
if (key) {
  sessionStorage.setItem("review-token", key);
  const url = new URL(location.href);
  url.searchParams.delete("key");
  history.replaceState({}, "", url);
}
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}
export async function api(path, method = "GET", data) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Review-Token": sessionStorage.getItem("review-token") || "",
      },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
  } catch {
    throw new ApiError("连接已中断，输入尚未保存。请重新启动服务后重试。", 0);
  }
  const result = await response.json();
  if (!response.ok)
    throw new ApiError(result.error || "操作失败", response.status);
  return result;
}
