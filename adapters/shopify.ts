<script>
!function(){
  try{
    var allowed = false;
    
    // 检查缓存
    var o=null;
    try{ 
      o=JSON.parse(sessionStorage.getItem("_fc")||"null");
    }catch(e){
      console.error('缓存解析失败:', e);
    }
    
    if(o&&o.e>Date.now()){
      if(o.m==="pass"){
        allowed=true;
      }else if(o.m==="redirect"&&o.u){
        location.replace(o.u);
        return;
      }else if(o.m==="deny"){
        document.open();
        document.write('<!DOCTYPE html><html><body style="margin:0"><div style="text-align:center;padding:100px;font:14px sans-serif"><h1>403 Forbidden</h1></div></body></html>');
        document.close();
        return;
      }
    }

    if(!allowed){
      // 生成指纹
      var r=document.cookie.match(/_sd_0000=([^;]+)/);
      var i="";
      if(r){
        i=decodeURIComponent(r[1]);
      }else{
        var a=navigator.userAgent||"";
        var c=(navigator.language||"").slice(0,5);
        var s=screen.width+"x"+screen.height;
        i="lite:"+function(e){
          for(var t=0,n=0;n<e.length;n++){
            var o=e.charCodeAt(n);
            t=(t<<5)-t+o;
            t|=0;
          }
          return(t>>>0).toString(36);
        }(a+"|"+s+"|"+c);
      }

      // 同步 XHR
      var u=new XMLHttpRequest;
      console.log('发起同步请求...');
      
      u.open("POST","https://gateway.foxfingerlab.com/v2/decide",false);
      u.setRequestHeader("Content-Type","application/json");
      u.setRequestHeader("X-App-Key","site_a7d1e487");
      
      var payload = JSON.stringify({
        context:{
          appId:2,
          ingress:"sdk",
          fingerprint:i,
          userAgent:navigator.userAgent,
          visitUrl:location.href,
          path:location.pathname,
          method:"GET",
          clientLanguage:navigator.language||null,
          repeatKey:"_sd_0000",
          repeatValue:i
        }
      });
      
      u.send(payload);
      
      console.log('请求完成, status:', u.status);

      if(u.status===200){
        var d;
        try{
          d=JSON.parse(u.responseText);
          d=d.data||d;
          console.log('响应数据:', d);
        }catch(parseErr){
          console.error('响应解析失败:', parseErr);
          allowed=true; // 降级：允许访问
        }
        
        if(d){
          // 缓存决策
          if(d.mechanism&&d.ttlSeconds>0){
            try{
              sessionStorage.setItem("_fc",JSON.stringify({
                m:d.mechanism,
                u:d.targetUrl,
                e:Date.now()+Math.min(d.ttlSeconds*1000,300000)
              }));
            }catch(cacheErr){
              console.error('缓存失败:', cacheErr);
            }
          }
          
          if(d.mechanism==="redirect"&&d.targetUrl){
            location.replace(d.targetUrl);
            return;
          }
          
          if(d.mechanism==="deny"){
            document.open();
            document.write('<!DOCTYPE html><html><body style="margin:0"><div style="text-align:center;padding:100px;font:14px sans-serif"><h1>403 Forbidden</h1></div></body></html>');
            document.close();
            return;
          }
          
          if(d.mechanism==="pass"){
            allowed=true;
          }
        }
      }else{
        console.warn('请求失败, status:', u.status);
        allowed=true; // 降级：允许访问
      }
    }

    // 如果到这里还不允许，显示空白（异常情况）
    if(!allowed){
      console.warn('未授权且无明确决策，降级允许访问');
      allowed=true;
    }
    
    console.log('脚本执行完成, allowed:', allowed);
    
  }catch(globalErr){
    console.error('全局错误:', globalErr);
    // 任何错误都降级为允许访问，避免页面完全不可用
  }
}();
</script>



<script>
!function(){
  var allowed=false,cache=null;
  try{cache=JSON.parse(sessionStorage.getItem("_fc")||"null")}catch(e){}

  if(cache&&cache.e>Date.now()){
    if(cache.m==="pass") allowed=true;
    else if(cache.m==="redirect"&&cache.u) return location.replace(cache.u);
    else if(cache.m==="deny"){
      document.documentElement.innerHTML='<body style="margin:0"><div style="text-align:center;padding:100px;font:14px sans-serif"><h1>403 Forbidden</h1></div></body>';
      return;
    }
  }

  if(!allowed){
    var ck=document.cookie.match(/_sd_0000=([^;]+)/),fp="";
    if(ck) fp=decodeURIComponent(ck[1]);
    else{
      var ua=navigator.userAgent||"",lang=(navigator.language||"").slice(0,5),scr=screen.width+"x"+screen.height;
      fp="lite:"+function(s){for(var h=0,i=0;i<s.length;i++){var c=s.charCodeAt(i);h=(h<<5)-h+c;h|=0}return(h>>>0).toString(36)}(ua+"|"+scr+"|"+lang);
    }

    var xhr=new XMLHttpRequest;
    try{
      xhr.open("POST","https://gateway.foxfingerlab.com/v2/decide",false);
      xhr.setRequestHeader("Content-Type","application/json");
      xhr.setRequestHeader("X-App-Key","site_eba8689a");
      xhr.send(JSON.stringify({context:{appId:1,ingress:"sdk",fingerprint:fp,userAgent:navigator.userAgent,visitUrl:location.href,path:location.pathname,method:"GET",clientLanguage:navigator.language||null,repeatKey:"_sd_0000",repeatValue:fp}}));

      if(xhr.status===200){
        var data;
        try{data=JSON.parse(xhr.responseText);data=data.data||data}catch(e){allowed=true}
        if(data){
          if(data.mechanism&&data.ttlSeconds>0){
            try{sessionStorage.setItem("_fc",JSON.stringify({m:data.mechanism,u:data.targetUrl,e:Date.now()+Math.min(data.ttlSeconds*1000,300000)}))}catch(e){}
          }
          if(data.mechanism==="redirect"&&data.targetUrl) return location.replace(data.targetUrl);
          if(data.mechanism==="deny"){
            document.documentElement.innerHTML='<body style="margin:0"><div style="text-align:center;padding:100px;font:14px sans-serif"><h1>403 Forbidden</h1></div></body>';
            return;
          }
          if(data.mechanism==="pass") allowed=true;
        }
      }else allowed=true;
    }catch(e){allowed=true}
  }

  if(!allowed){
    var s=document.createElement("style");
    s.id="_fh";
    s.textContent="html{visibility:hidden!important}";
    (document.head||document.documentElement).appendChild(s);
    setTimeout(function(){var e=document.getElementById("_fh");e&&e.remove()},6000);
  }
}();
</script>