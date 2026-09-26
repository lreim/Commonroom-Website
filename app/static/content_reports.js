(() => {
  const dialog = document.getElementById('content-report-dialog');
  if (!dialog) return;
  const submit = document.getElementById('content-report-submit');
  const status = document.getElementById('content-report-status');
  let targetUrl = null;
  let pending = false;
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-report-url]');
    if (!trigger || pending) return;
    targetUrl = trigger.dataset.reportUrl;
    status.textContent = '';
    submit.disabled = false;
    submit.hidden = false;
    submit.textContent = 'Report';
    dialog.showModal();
  });
  dialog.querySelector('[data-report-close]').addEventListener('click', () => dialog.close());
  submit.addEventListener('click', async () => {
    if (pending || !targetUrl) return;
    pending = true;
    submit.disabled = true;
    submit.textContent = 'Reporting…';
    status.textContent = '';
    try {
      const response = await fetch(targetUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
      });
      if (response.redirected) throw new Error('Please sign in again to report this message.');
      if (!response.ok) throw new Error('The report could not be submitted. Please try again.');
      const data = await response.json();
      status.textContent = data.message;
      submit.hidden = true;
    } catch (error) {
      status.textContent = error.message;
      submit.disabled = false;
    } finally {
      pending = false;
      submit.textContent = 'Report';
    }
  });
})();
