
import {useState} from 'react'
const API = "http://localhost:8000"

export default function(){
 const [file,setFile]=useState(null)
 const [cols,setCols]=useState([])
 const [dni,setDni]=useState("")
 const [fecha,setFecha]=useState("")
 const [vis,setVis]=useState([])
 const [pw,setPw]=useState("")

 async function subir(){
  const f=new FormData(); f.append("file",file)
  const r=await fetch(API+"/admin/upload",{method:'POST',body:f,headers:{'X-Admin-Password':pw}})
  const d=await r.json(); setCols(d.columns)
 }
 async function guardar(){
  const f=new FormData()
  f.append("dni_col",dni);f.append("fecha_col",fecha);f.append("visibles",JSON.stringify(vis))
  await fetch(API+"/admin/config",{method:'POST',body:f,headers:{'X-Admin-Password':pw}})
  alert("Configurado")
 }
 return (<div>
  <h2>Admin</h2>
  <input type="password" placeholder="Password" onChange={e=>setPw(e.target.value)}/><br/>
  <input type="file" onChange={e=>setFile(e.target.files[0])}/>
  <button onClick={subir}>Subir Excel</button><hr/>
  DNI: <select onChange={e=>setDni(e.target.value)}>{cols.map(c=><option>{c}</option>)}</select><br/>
  FECHA: <select onChange={e=>setFecha(e.target.value)}>{cols.map(c=><option>{c}</option>)}</select><br/>
  VISIBLES:{cols.map(c=><div><input type="checkbox" onChange={e=>{
    if(e.target.checked) setVis([...vis,c]); else setVis(vis.filter(x=>x!=c))
  }}/>{c}</div>)}
  <button onClick={guardar}>Guardar</button>
 </div>)
}
