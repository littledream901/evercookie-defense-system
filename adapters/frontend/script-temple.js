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