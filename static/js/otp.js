(function(){
  function getCookie(name){
    if(!document.cookie) return null;
    var c = document.cookie.split(';').map(s=>s.trim());
    for(var i=0;i<c.length;i++){var parts=c[i].split('='); if(parts[0]===name) return decodeURIComponent(parts[1]);}
    return null;
  }

  function jsonPost(url, data){
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-CSRFToken': getCookie('csrftoken') || ''
      },
      body: new URLSearchParams(data)
    }).then(r=>r.json().then(j=>({ok:r.ok,status:r.status,body:j}))).catch(e=>({ok:false,error:e.message}));
  }

  function attach(widget){
    var sendBtn = widget.querySelector('[data-otp-action="send"]');
    var verifyBtn = widget.querySelector('[data-otp-action="verify"]');
    var phoneInput = widget.querySelector('input[name="otp_phone"]');
    var codeInput = widget.querySelector('input[name="otp_code"]');
    var stateSend = widget.querySelector('.otp-state-send');
    var stateVerify = widget.querySelector('.otp-state-verify');
    var feedback = widget.querySelector('.otp-feedback');
    var resendBtn = widget.querySelector('[data-otp-action="resend"]');
    var resendTimerEl = widget.querySelector('.otp-resend-timer');
    var resendSecondsEl = widget.querySelector('.otp-resend-seconds');
    var expiryDisplay = widget.querySelector('.otp-expiry-display');

    var expirySeconds = parseInt(widget.dataset.expiry || widget.getAttribute('data-expiry') || '300', 10);
    var resendCooldown = parseInt(widget.dataset.resend || widget.getAttribute('data-resend') || '60', 10);
    var expiryInterval = null;
    var resendInterval = null;

    function showFeedback(msg, level){
      feedback.innerText = msg;
      feedback.className = 'otp-feedback mt-3 ' + (level ? ('text-' + level + '-600') : 'text-gray-600');
    }

    sendBtn.addEventListener('click', function(){
      var phone = phoneInput.value.trim();
      if(!phone){ showFeedback('شماره موبایل را وارد کنید.', 'red'); return; }
      sendBtn.disabled = true;
      showFeedback('در حال ارسال…');
      jsonPost('/accounts/otp/send/', {phone: phone}).then(function(res){
        sendBtn.disabled = false;
        if(res.ok && res.body && res.body.ok){
          showFeedback('کد با موفقیت ارسال شد. کد را وارد کنید.', 'green');
          stateSend.classList.add('hidden');
          stateVerify.classList.remove('hidden');
          codeInput.focus();
          startExpiryTimer(expirySeconds);
          startResendCooldown(resendCooldown);
        }else{
          var msg = (res.body && res.body.error) ? res.body.error : 'خطا در ارسال کد';
          showFeedback(msg, 'red');
        }
      });
    });

    verifyBtn.addEventListener('click', function(){
      var phone = phoneInput.value.trim();
      var code = codeInput.value.trim();
      if(!phone || !code){ showFeedback('شماره و کد را وارد کنید.', 'red'); return; }
      verifyBtn.disabled = true;
      showFeedback('در حال بررسی…');
      jsonPost('/accounts/otp/verify-login/', {phone: phone, code: code}).then(function(res){
        verifyBtn.disabled = false;
        if(res.ok && res.body && res.body.ok){
          showFeedback('احراز هویت موفق — در حال هدایت...', 'green');
          setTimeout(function(){ window.location.reload(); }, 600);
        }else{
          var msg = (res.body && res.body.error) ? res.body.error : 'خطا در تایید کد';
          showFeedback(msg, 'red');
        }
      });
    });

    // resend handler (client-side only - will call send endpoint again if allowed)
    if(resendBtn){
      resendBtn.addEventListener('click', function(){
        resendBtn.disabled = true;
        sendBtn.click();
      });
    }

    function startExpiryTimer(seconds){
      clearInterval(expiryInterval);
      var s = seconds;
      if(expiryDisplay) expiryDisplay.innerText = s;
      expiryInterval = setInterval(function(){
        s -= 1;
        if(expiryDisplay) expiryDisplay.innerText = s;
        if(s <= 0){
          clearInterval(expiryInterval);
          showFeedback('کد منقضی شد. دوباره ارسال کنید.', 'red');
          stateVerify.classList.add('hidden');
          stateSend.classList.remove('hidden');
        }
      }, 1000);
    }

    function startResendCooldown(seconds){
      clearInterval(resendInterval);
      var s = seconds;
      if(resendBtn) resendBtn.disabled = true;
      if(resendTimerEl){ resendTimerEl.classList.remove('hidden'); resendSecondsEl.innerText = s; }
      resendInterval = setInterval(function(){
        s -= 1; if(resendSecondsEl) resendSecondsEl.innerText = s;
        if(s <= 0){
          clearInterval(resendInterval);
          if(resendBtn) resendBtn.disabled = false;
          if(resendTimerEl) resendTimerEl.classList.add('hidden');
        }
      }, 1000);
    }
  }

  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.otp-widget').forEach(function(w){ attach(w); });
  });
})();
