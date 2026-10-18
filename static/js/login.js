document.getElementById('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const username = form.elements.username.value.trim();
  const password = form.elements.password.value;
  const message = document.getElementById('login-message');
  if (!username) {
    message.textContent = '请输入有效账号。';
    message.className = 'message warning';
    message.hidden = false;
    return;
  }
  const button = form.querySelector('[type="submit"]');
  if (button.disabled) return;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = '正在登录…';
  message.hidden = true;
  try {
    await apiRequest('/login', 'POST', {username, password});
    window.location.assign('/dashboard');
  } catch (error) {
    message.textContent = error.message;
    message.className = 'message error';
    message.hidden = false;
  } finally {
    form.elements.password.value = '';
    button.disabled = false;
    button.textContent = label;
  }
});
