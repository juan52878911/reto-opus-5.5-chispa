# Tabla de resultados desde el CSV de correr.sh (-v stub=0|1). Errores=-1 = tanda fallida: fuera de las medias.
NR>1{k=$1","$2; if(!(k in ord)){ord[k]=++m; key[m]=k}
  if($9<0){f[k]++; next}
  n[k]++; d[k]+=$4; pt[k]+=$5; p5[k]+=$6; if($7>p9[k])p9[k]=$7; e[k]+=$9}
END{for(i=1;i<=m;i++){k=key[i]; split(k,a,",");
  if(!n[k]){printf "| %s | %s | FALLÓ | - | - | - | - | 0 (+%d fallidas) | FALLÓ |\n",a[1],a[2],f[k]; continue}
  dd=d[k]/n[k]; ok="-";
  if(a[1]=="l1") ok=(dd>=5000&&p9[k]<20)?"cumple":"NO cumple"; else if(a[1]=="l2") ok=stub?"n/a (L2 stub)":(dd>=300)?"cumple":"NO cumple";
  if(f[k]) ok=ok" · FALLÓ "f[k]" tanda(s)";
  printf "| %s | %s | %.0f | %.0f | %.3f | %.3f | %d | %d | %s |\n",a[1],a[2],dd,pt[k]/n[k],p5[k]/n[k],p9[k],e[k],n[k],ok}}
