import{q as ln,s as Ye,v as dn,d as Ee,x as un,y as cn,h as I,z as fn,a as N,A as bn,D as pn,E as vn,G as hn,H as j,J as l,K as tt,o as i,c as v,g as P,L as E,M as Ot,N as mn,O as Me,P as Ne,Q as Bt,e as Ie,R as Ae,S as He,T as pt,U as Qe,V as A,W as gn,X as vt,Y as Ze,Z as ht,$ as ze,a0 as yn,n as Fe,a1 as At,a2 as xn,m as et,F as Z,a3 as wn,a4 as Sn,a5 as Cn,a6 as g,a7 as fe,a8 as kn,B as We,a9 as nt,aa as at,ab as Rn,f as Lt,ac as Tn,ad as _n,ae as $n,af as mt,ag as Be,ah as qe,ai as Pn,aj as zn,ak as In,al as On,w as se,u as J,am as Bn,j as re,t as le,b as _e,k as $e,r as rt,C as An,l as Ln,I as Nn,an as En,p as Vn,_ as jn}from"./index-k2JXiZDX.js";import{T as gt}from"./Tag-XrDlKYZ8.js";import{u as yt,S as Mn,A as ot}from"./Spin-BoZ3jk5N.js";import{I as Xe}from"./Input-B1WMA47P.js";import{c as Wn,a as xt,u as Fn,b as Nt,o as Dn,S as Un}from"./Select-6MhKkqZw.js";import{T as Hn}from"./Tooltip-DwXUtJ85.js";import{u as Jn}from"./use-message-XmbKjm3k.js";import{A as Et}from"./Add-kjvKLW1w.js";import{S as wt}from"./Switch-MvJz3qG2.js";import{C as Gn}from"./ChevronLeft-w50E5lSp.js";import{C as Kn}from"./ChevronRight-BXmkUSvh.js";var qn=/\s/;function Xn(e){for(var o=e.length;o--&&qn.test(e.charAt(o)););return o}var Yn=/^\s+/;function Qn(e){return e&&e.slice(0,Xn(e)+1).replace(Yn,"")}var St=NaN,Zn=/^[-+]0x[0-9a-f]+$/i,ea=/^0b[01]+$/i,ta=/^0o[0-7]+$/i,na=parseInt;function Ct(e){if(typeof e=="number")return e;if(ln(e))return St;if(Ye(e)){var o=typeof e.valueOf=="function"?e.valueOf():e;e=Ye(o)?o+"":o}if(typeof e!="string")return e===0?e:+e;e=Qn(e);var f=ea.test(e);return f||ta.test(e)?na(e.slice(2),f?2:8):Zn.test(e)?St:+e}var it=function(){return dn.Date.now()},aa="Expected a function",ra=Math.max,oa=Math.min;function ia(e,o,f){var w,p,_,S,y,C,b=0,D=!1,O=!1,Y=!0;if(typeof e!="function")throw new TypeError(aa);o=Ct(o)||0,Ye(f)&&(D=!!f.leading,O="maxWait"in f,_=O?ra(Ct(f.maxWait)||0,o):_,Y="trailing"in f?!!f.trailing:Y);function te($){var K=w,k=p;return w=p=void 0,b=$,S=e.apply(k,K),S}function G($){return b=$,y=setTimeout(L,o),D?te($):S}function U($){var K=$-C,k=$-b,q=o-K;return O?oa(q,_-k):q}function M($){var K=$-C,k=$-b;return C===void 0||K>=o||K<0||O&&k>=_}function L(){var $=it();if(M($))return me($);y=setTimeout(L,U($))}function me($){return y=void 0,Y&&w?te($):(w=p=void 0,S)}function Te(){y!==void 0&&clearTimeout(y),b=0,w=C=p=y=void 0}function ge(){return y===void 0?S:me(it())}function oe(){var $=it(),K=M($);if(w=arguments,p=this,C=$,K){if(y===void 0)return G(C);if(O)return clearTimeout(y),y=setTimeout(L,o),te(C)}return y===void 0&&(y=setTimeout(L,o)),S}return oe.cancel=Te,oe.flush=ge,oe}var sa="Expected a function";function la(e,o,f){var w=!0,p=!0;if(typeof e!="function")throw new TypeError(sa);return Ye(f)&&(w="leading"in f?!!f.leading:w,p="trailing"in f?!!f.trailing:p),ia(e,o,{leading:w,maxWait:o,trailing:p})}const da=xt(".v-x-scroll",{overflow:"auto",scrollbarWidth:"none"},[xt("&::-webkit-scrollbar",{width:0,height:0})]),ua=Ee({name:"XScroll",props:{disabled:Boolean,onScroll:Function},setup(){const e=I(null);function o(p){!(p.currentTarget.offsetWidth<p.currentTarget.scrollWidth)||p.deltaY===0||(p.currentTarget.scrollLeft+=p.deltaY+p.deltaX,p.preventDefault())}const f=cn();return da.mount({id:"vueuc/x-scroll",head:!0,anchorMetaName:Wn,ssr:f}),Object.assign({selfRef:e,handleWheel:o},{scrollTo(...p){var _;(_=e.value)===null||_===void 0||_.scrollTo(...p)}})},render(){return un("div",{ref:"selfRef",onScroll:this.onScroll,onWheel:this.disabled?void 0:this.handleWheel,class:"v-x-scroll"},this.$slots)}});var ca=Ee({name:"Remove",render(){return(()=>{const e=fn("a77472467b8adb0a");return e[0]||(e[0]=N("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 512 512"},[N("line",{x1:"400",y1:"256",x2:"112",y2:"256",style:`
        fill: none;
        stroke: currentColor;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-width: 32px;
      `})],-1))})()}});function fa(e){const{textColorDisabled:o}=e;return{iconColorDisabled:o}}const ba=bn({name:"InputNumber",common:hn,peers:{Button:vn,Input:pn},self:fa});var pa=j([l("input-number-suffix",`
 display: inline-block;
 margin-right: 10px;
 `),l("input-number-prefix",`
 display: inline-block;
 margin-left: 10px;
 `)]);function va(e){return e==null||typeof e=="string"&&e.trim()===""?null:Number(e)}function ha(e){return e.includes(".")&&(/^(-)?\d+.*(\.|0)$/.test(e)||/^-?\d*$/.test(e))||e==="-"||e==="-0"}function st(e){return e==null?!0:!Number.isNaN(e)}function kt(e,o){return typeof e!="number"?"":o===void 0?String(e):e.toFixed(o)}function lt(e){if(e===null)return null;if(typeof e=="number")return e;{const o=Number(e);return Number.isNaN(o)?null:o}}const Rt=800,Tt=100,ma={...tt.props,autofocus:Boolean,loading:{type:Boolean,default:void 0},placeholder:String,defaultValue:{type:Number,default:null},value:Number,step:{type:[Number,String],default:1},min:[Number,String],max:[Number,String],size:String,disabled:{type:Boolean,default:void 0},validator:Function,bordered:{type:Boolean,default:void 0},showButton:{type:Boolean,default:!0},buttonPlacement:{type:String,default:"right"},inputProps:Object,readonly:Boolean,clearable:Boolean,keyboard:{type:Object,default:{}},updateValueOnInput:{type:Boolean,default:!0},round:{type:Boolean,default:void 0},parse:Function,format:Function,precision:Number,status:String,"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],onFocus:[Function,Array],onBlur:[Function,Array],onClear:[Function,Array],onChange:[Function,Array]};var ga=Ee({name:"InputNumber",props:ma,slots:Object,setup(e){const{mergedBorderedRef:o,mergedClsPrefixRef:f,mergedRtlRef:w,mergedComponentPropsRef:p}=Ot(e),_=tt("InputNumber","-input-number",pa,ba,e,f),{localeRef:S}=Fn("InputNumber"),y=mn(e,{mergedSize:r=>{var ce,we;const{size:d}=e;if(d)return d;const{mergedSize:T}=r||{};if(T!=null&&T.value)return T.value;const ie=(we=(ce=p==null?void 0:p.value)==null?void 0:ce.InputNumber)==null?void 0:we.size;return ie||"medium"}}),{mergedSizeRef:C,mergedDisabledRef:b,mergedStatusRef:D}=y,O=I(null),Y=I(null),te=I(null),G=I(e.defaultValue),U=ze(e,"value"),M=Nt(U,G),L=I(""),me=r=>{const d=String(r).split(".")[1];return d?d.length:0},Te=r=>{const d=[e.min,e.max,e.step,r].map(T=>T===void 0?0:me(T));return Math.max(...d)},ge=Me(()=>{const{placeholder:r}=e;return r!==void 0?r:S.value.placeholder}),oe=Me(()=>{const r=lt(e.step);return r!==null?r===0?1:Math.abs(r):1}),$=Me(()=>{const r=lt(e.min);return r!==null?r:null}),K=Me(()=>{const r=lt(e.max);return r!==null?r:null}),k=()=>{const{value:r}=M;if(st(r)){const{format:d,precision:T}=e;d?L.value=d(r):r===null||T===void 0||me(r)>T?L.value=kt(r,void 0):L.value=kt(r,T)}else L.value=String(r)};k();const q=r=>{const{value:d}=M;if(r===d){k();return}const{"onUpdate:value":T,onUpdateValue:ie,onChange:ce}=e,{nTriggerFormInput:we,nTriggerFormChange:Le}=y;ce&&Ae(ce,r),ie&&Ae(ie,r),T&&Ae(T,r),G.value=r,we(),Le()},be=({offset:r,doUpdateIfValid:d,fixPrecision:T,isInputing:ie})=>{const{value:ce}=L;if(ie&&ha(ce))return!1;const we=(e.parse||va)(ce);if(we===null)return d&&q(null),null;if(st(we)){const Le=me(we),{precision:Ge}=e;if(Ge!==void 0&&Ge<Le&&!T)return!1;let Pe=Number.parseFloat((we+r).toFixed(Ge??Te(we)));if(st(Pe)){const{value:Oe}=K,{value:Ue}=$;if(Oe!==null&&Pe>Oe){if(!d||ie)return!1;Pe=Oe}if(Ue!==null&&Pe<Ue){if(!d||ie)return!1;Pe=Ue}return e.validator&&!e.validator(Pe)?!1:(d&&q(Pe),Pe)}}return!1},ye=Me(()=>be({offset:0,doUpdateIfValid:!1,isInputing:!1,fixPrecision:!1})===!1),B=Me(()=>{const{value:r}=M;if(e.validator&&r===null)return!1;const{value:d}=oe;return be({offset:-d,doUpdateIfValid:!1,isInputing:!1,fixPrecision:!1})!==!1}),X=Me(()=>{const{value:r}=M;if(e.validator&&r===null)return!1;const{value:d}=oe;return be({offset:+d,doUpdateIfValid:!1,isInputing:!1,fixPrecision:!1})!==!1});function ve(r){const{onFocus:d}=e,{nTriggerFormFocus:T}=y;d&&Ae(d,r),T()}function Ve(r){var ce,we;if(r.target===((ce=O.value)==null?void 0:ce.wrapperElRef))return;const d=be({offset:0,doUpdateIfValid:!0,isInputing:!1,fixPrecision:!0});if(d!==!1){const Le=(we=O.value)==null?void 0:we.inputElRef;Le&&(Le.value=String(d||"")),M.value===d&&k()}else k();const{onBlur:T}=e,{nTriggerFormBlur:ie}=y;T&&Ae(T,r),ie(),He(()=>{k()})}function xe(r){const{onClear:d}=e;d&&Ae(d,r)}function Se(){const{value:r}=X;if(!r){de();return}const{value:d}=M;if(d===null)e.validator||q(De());else{const{value:T}=oe;be({offset:T,doUpdateIfValid:!0,isInputing:!1,fixPrecision:!0})}}function Ce(){const{value:r}=B;if(!r){m();return}const{value:d}=M;if(d===null)e.validator||q(De());else{const{value:T}=oe;be({offset:-T,doUpdateIfValid:!0,isInputing:!1,fixPrecision:!0})}}const Je=ve,je=Ve;function De(){if(e.validator)return null;const{value:r}=$,{value:d}=K;return r!==null?Math.max(0,r):d!==null?Math.min(0,d):0}function s(r){xe(r),q(null)}function n(r){var d,T,ie;(d=te.value)!=null&&d.$el.contains(r.target)&&r.preventDefault(),(T=Y.value)!=null&&T.$el.contains(r.target)&&r.preventDefault(),(ie=O.value)==null||ie.activate()}let c=null,h=null,R=null;function m(){R&&(window.clearTimeout(R),R=null),c&&(window.clearInterval(c),c=null)}let z=null;function de(){z&&(window.clearTimeout(z),z=null),h&&(window.clearInterval(h),h=null)}function Q(){m(),R=window.setTimeout(()=>{c=window.setInterval(()=>{Ce()},Tt)},Rt),pt("mouseup",document,m,{once:!0})}function ke(){de(),z=window.setTimeout(()=>{h=window.setInterval(()=>{Se()},Tt)},Rt),pt("mouseup",document,de,{once:!0})}const ne=()=>{h||Se()},W=()=>{c||Ce()};function he(r){var d,T;if(r.key==="Enter"){if(r.target===((d=O.value)==null?void 0:d.wrapperElRef))return;be({offset:0,doUpdateIfValid:!0,isInputing:!1,fixPrecision:!0})!==!1&&((T=O.value)==null||T.deactivate())}else if(r.key==="ArrowUp"){if(!X.value||e.keyboard.ArrowUp===!1)return;r.preventDefault(),be({offset:0,doUpdateIfValid:!0,isInputing:!1,fixPrecision:!0})!==!1&&Se()}else if(r.key==="ArrowDown"){if(!B.value||e.keyboard.ArrowDown===!1)return;r.preventDefault(),be({offset:0,doUpdateIfValid:!0,isInputing:!1,fixPrecision:!0})!==!1&&Ce()}}function V(r){L.value=r,e.updateValueOnInput&&!e.format&&!e.parse&&e.precision===void 0&&be({offset:0,doUpdateIfValid:!0,isInputing:!0,fixPrecision:!1})}Ne(M,()=>{k()});const ae={focus:()=>{var r;return(r=O.value)==null?void 0:r.focus()},blur:()=>{var r;return(r=O.value)==null?void 0:r.blur()},select:()=>{var r;return(r=O.value)==null?void 0:r.select()}},ue=Bt("InputNumber",w,f);return{...ae,rtlEnabled:ue,inputInstRef:O,minusButtonInstRef:Y,addButtonInstRef:te,mergedClsPrefix:f,mergedBordered:o,uncontrolledValue:G,mergedValue:M,mergedPlaceholder:ge,displayedValueInvalid:ye,mergedSize:C,mergedDisabled:b,displayedValue:L,addable:X,minusable:B,mergedStatus:D,handleFocus:Je,handleBlur:je,handleClear:s,handleMouseDown:n,handleAddClick:ne,handleMinusClick:W,handleAddMousedown:ke,handleMinusMousedown:Q,handleKeyDown:he,handleUpdateDisplayedValue:V,mergedTheme:_,inputThemeOverrides:{paddingSmall:"0 8px 0 10px",paddingMedium:"0 8px 0 12px",paddingLarge:"0 8px 0 14px"},buttonThemeOverrides:Ie(()=>{const{self:{iconColorDisabled:r}}=_.value,[d,T,ie,ce]=gn(r);return{textColorTextDisabled:`rgb(${d}, ${T}, ${ie})`,opacityDisabled:`${ce}`}})}},render(){const{mergedClsPrefix:e,$slots:o}=this,f=()=>(i(),P(ht,{text:!0,disabled:!this.minusable||this.mergedDisabled||this.readonly,focusable:!1,theme:this.mergedTheme.peers.Button,themeOverrides:this.mergedTheme.peerOverrides.Button,builtinThemeOverrides:this.buttonThemeOverrides,onClick:this.handleMinusClick,onMousedown:this.handleMinusMousedown,ref:"minusButtonInstRef"},{icon:()=>vt(o["minus-icon"],()=>[(i(),P(Ze,{clsPrefix:e},{default:()=>(i(),P(ca))},1032,["clsPrefix"]))])},1032,["disabled","theme","themeOverrides","builtinThemeOverrides","onClick","onMousedown"])),w=()=>(i(),P(ht,{text:!0,disabled:!this.addable||this.mergedDisabled||this.readonly,focusable:!1,theme:this.mergedTheme.peers.Button,themeOverrides:this.mergedTheme.peerOverrides.Button,builtinThemeOverrides:this.buttonThemeOverrides,onClick:this.handleAddClick,onMousedown:this.handleAddMousedown,ref:"addButtonInstRef"},{icon:()=>vt(o["add-icon"],()=>[(i(),P(Ze,{clsPrefix:e},{default:()=>(i(),P(Et))},1032,["clsPrefix"]))])},1032,["disabled","theme","themeOverrides","builtinThemeOverrides","onClick","onMousedown"]));return i(),v("div",{class:E([`${e}-input-number`,this.rtlEnabled&&`${e}-input-number--rtl`])},[(i(),P(Xe,{ref:"inputInstRef",autofocus:this.autofocus,status:this.mergedStatus,bordered:this.mergedBordered,loading:this.loading,value:this.displayedValue,onUpdateValue:this.handleUpdateDisplayedValue,theme:this.mergedTheme.peers.Input,themeOverrides:this.mergedTheme.peerOverrides.Input,builtinThemeOverrides:this.inputThemeOverrides,size:this.mergedSize,placeholder:this.mergedPlaceholder,disabled:this.mergedDisabled,readonly:this.readonly,round:this.round,textDecoration:this.displayedValueInvalid?"line-through":void 0,onFocus:this.handleFocus,onBlur:this.handleBlur,onKeydown:this.handleKeyDown,onMousedown:this.handleMouseDown,onClear:this.handleClear,clearable:this.clearable,inputProps:this.inputProps,internalLoadingBeforeSuffix:!0},{prefix:()=>{var p;return this.showButton&&this.buttonPlacement==="both"?[f(),Qe(o.prefix,_=>_?(i(),v("span",{key:1,class:E(`${e}-input-number-prefix`)},[A(()=>_)],2)):null)]:(p=o.prefix)==null?void 0:p.call(o)},suffix:()=>{var p;return this.showButton?[Qe(o.suffix,_=>_?(i(),v("span",{key:2,class:E(`${e}-input-number-suffix`)},[A(()=>_)],2)):null),this.buttonPlacement==="right"?f():null,w()]:(p=o.suffix)==null?void 0:p.call(o)}},1032,["autofocus","status","bordered","loading","value","onUpdateValue","theme","themeOverrides","builtinThemeOverrides","size","placeholder","disabled","readonly","round","textDecoration","onFocus","onBlur","onKeydown","onMousedown","onClear","clearable","inputProps"]))],2)}});const ft=yn("n-tabs"),Vt={tab:[String,Number,Object,Function],name:{type:[String,Number],required:!0},disabled:Boolean,displayDirective:{type:String,default:"if"},closable:{type:Boolean,default:void 0},tabProps:Object,label:[String,Number,Object,Function]};var ya=Ee({__TAB_PANE__:!0,name:"TabPane",alias:["TabPanel"],props:Vt,slots:Object,setup(e){const o=At(ft,null);return o||xn("tab-pane","`n-tab-pane` must be placed inside `n-tabs`."),{style:o.paneStyleRef,class:o.paneClassRef,mergedClsPrefix:o.mergedClsPrefixRef}},render(){return i(),v("div",{class:E([`${this.mergedClsPrefix}-tab-pane`,this.class]),style:Fe(this.style)},[A(()=>{var e,o;return(o=(e=this.$slots).default)==null?void 0:o.call(e)})],6)}});const xa=["data-name","data-disabled"],wa={internalLeftPadded:Boolean,internalAddable:Boolean,internalCreatedByPane:Boolean,...Cn(Vt,["displayDirective"])};var ct=Ee({__TAB__:!0,inheritAttrs:!1,name:"Tab",props:wa,setup(e){const{mergedClsPrefixRef:o,valueRef:f,typeRef:w,closableRef:p,tabStyleRef:_,addTabStyleRef:S,tabClassRef:y,addTabClassRef:C,tabChangeIdRef:b,onBeforeLeaveRef:D,triggerRef:O,handleAdd:Y,activateTab:te,handleClose:G}=At(ft);return{trigger:O,mergedClosable:Ie(()=>{if(e.internalAddable)return!1;const{closable:U}=e;return U===void 0?p.value:U}),style:_,addStyle:S,tabClass:y,addTabClass:C,clsPrefix:o,value:f,type:w,handleClose(U){U.stopPropagation(),!e.disabled&&G(e.name)},activateTab(){if(e.disabled)return;if(e.internalAddable){Y();return}const{name:U}=e,M=++b.id;if(U!==f.value){const{value:L}=D;L?Promise.resolve(L(e.name,f.value)).then(me=>{me&&b.id===M&&te(U)}):te(U)}}}},render(){const{internalAddable:e,clsPrefix:o,name:f,disabled:w,label:p,tab:_,value:S,mergedClosable:y,trigger:C,$slots:{default:b}}=this,D=p??_;return i(),v("div",{class:E(`${o}-tabs-tab-wrapper`)},[this.internalLeftPadded?(i(),v("div",{key:0,class:E(`${o}-tabs-tab-pad`)},null,2)):A(()=>null),(i(),v("div",et({key:f,"data-name":f,"data-disabled":w?!0:void 0},et({class:[`${o}-tabs-tab`,S===f&&`${o}-tabs-tab--active`,w&&`${o}-tabs-tab--disabled`,y&&`${o}-tabs-tab--closable`,e&&`${o}-tabs-tab--addable`,e?this.addTabClass:this.tabClass],onClick:C==="click"?this.activateTab:void 0,onMouseenter:C==="hover"?this.activateTab:void 0,style:e?this.addStyle:this.style},this.internalCreatedByPane?this.tabProps||{}:this.$attrs)),[N("span",{class:E(`${o}-tabs-tab__label`)},[e?(i(),v(Z,{key:0},[N("div",{class:E(`${o}-tabs-tab__height-placeholder`)}," ",2),(i(),P(Ze,{clsPrefix:o},{default:()=>(i(),P(Et))},1032,["clsPrefix"]))],64)):(i(),v(Z,{key:1},[b?(i(),v(Z,{key:0},[A(()=>b())],64)):(i(),v(Z,{key:1},[typeof D=="object"?(i(),v(Z,{key:0},[A(()=>D)],64)):(i(),v(Z,{key:1},[A(()=>wn(D??f))],64))],64))],64))],2),y&&this.type==="card"?(i(),P(Sn,{key:0,clsPrefix:o,class:E(`${o}-tabs-tab__close`),onClick:this.handleClose,disabled:w},null,8,["clsPrefix","class","onClick","disabled"])):A(()=>null)],16,xa))],2)}}),Sa=l("tabs",`
 box-sizing: border-box;
 width: 100%;
 display: flex;
 flex-direction: column;
 transition:
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
`,[j("&.transition-disabled",[l("tabs-tab",`
 transition: none !important;
 `),l("tabs-nav-scroll-content",`
 transition: none !important;
 `),l("tabs-tab-pad",`
 transition: none !important;
 `)]),g("segment-type",[l("tabs-rail",[j("&.transition-disabled",[l("tabs-capsule",`
 transition: none;
 `)])])]),g("top",[l("tab-pane",`
 padding: var(--n-pane-padding-top) var(--n-pane-padding-right) var(--n-pane-padding-bottom) var(--n-pane-padding-left);
 `)]),g("left",[l("tab-pane",`
 padding: var(--n-pane-padding-right) var(--n-pane-padding-bottom) var(--n-pane-padding-left) var(--n-pane-padding-top);
 `)]),g("left, right",`
 flex-direction: row;
 `,[l("tabs-bar",`
 width: 2px;
 right: 0;
 transition:
 top .2s var(--n-bezier),
 max-height .2s var(--n-bezier),
 background-color .3s var(--n-bezier);
 `),l("tabs-tab",`
 padding: var(--n-tab-padding-vertical); 
 `)]),g("right",`
 flex-direction: row-reverse;
 `,[l("tab-pane",`
 padding: var(--n-pane-padding-left) var(--n-pane-padding-top) var(--n-pane-padding-right) var(--n-pane-padding-bottom);
 `),l("tabs-bar",`
 left: 0;
 `)]),g("bottom",`
 flex-direction: column-reverse;
 justify-content: flex-end;
 `,[l("tab-pane",`
 padding: var(--n-pane-padding-bottom) var(--n-pane-padding-right) var(--n-pane-padding-top) var(--n-pane-padding-left);
 `),l("tabs-bar",`
 top: 0;
 `)]),l("tabs-rail",`
 position: relative;
 padding: 3px;
 border-radius: var(--n-tab-border-radius);
 width: 100%;
 background-color: var(--n-color-segment);
 transition: background-color .3s var(--n-bezier);
 display: flex;
 align-items: center;
 `,[l("tabs-capsule",`
 border-radius: var(--n-tab-border-radius);
 position: absolute;
 left: 0;
 top: 0;
 pointer-events: none;
 background-color: var(--n-tab-color-segment);
 box-shadow: 0 1px 3px 0 rgba(0, 0, 0, .08);
 transition: transform 0.3s var(--n-bezier);
 `),l("tabs-tab-wrapper",`
 flex-basis: 0;
 flex-grow: 1;
 display: flex;
 align-items: center;
 justify-content: center;
 `,[l("tabs-tab",`
 overflow: hidden;
 border-radius: var(--n-tab-border-radius);
 width: 100%;
 display: flex;
 align-items: center;
 justify-content: center;
 `,[g("active",`
 font-weight: var(--n-font-weight-strong);
 color: var(--n-tab-text-color-active);
 `),j("&:hover",`
 color: var(--n-tab-text-color-hover);
 `)])])]),g("flex",[l("tabs-nav",`
 width: 100%;
 position: relative;
 `,[l("tabs-wrapper",`
 width: 100%;
 `,[l("tabs-tab",`
 margin-right: 0;
 `)])])]),l("tabs-nav",`
 box-sizing: border-box;
 line-height: 1.5;
 display: flex;
 transition: border-color .3s var(--n-bezier);
 `,[fe("prefix, suffix",`
 display: flex;
 align-items: center;
 `),fe("prefix","padding-right: 16px;"),fe("suffix","padding-left: 16px;")]),g("top, bottom",[j(">",[l("tabs-nav",[l("tabs-nav-scroll-wrapper",[j("&::before",`
 top: 0;
 bottom: 0;
 left: 0;
 width: 20px;
 `),j("&::after",`
 top: 0;
 bottom: 0;
 right: 0;
 width: 20px;
 `),g("shadow-start",[j("&::before",`
 box-shadow: inset 10px 0 8px -8px rgba(0, 0, 0, .12);
 `)]),g("shadow-end",[j("&::after",`
 box-shadow: inset -10px 0 8px -8px rgba(0, 0, 0, .12);
 `)])])])])]),g("left, right",[l("tabs-nav-scroll-content",`
 flex-direction: column;
 `),j(">",[l("tabs-nav",[l("tabs-nav-scroll-wrapper",[j("&::before",`
 top: 0;
 left: 0;
 right: 0;
 height: 20px;
 `),j("&::after",`
 bottom: 0;
 left: 0;
 right: 0;
 height: 20px;
 `),g("shadow-start",[j("&::before",`
 box-shadow: inset 0 10px 8px -8px rgba(0, 0, 0, .12);
 `)]),g("shadow-end",[j("&::after",`
 box-shadow: inset 0 -10px 8px -8px rgba(0, 0, 0, .12);
 `)])])])])]),l("tabs-nav-scroll-wrapper",`
 flex: 1;
 position: relative;
 overflow: hidden;
 `,[l("tabs-nav-y-scroll",`
 height: 100%;
 width: 100%;
 overflow-y: auto; 
 scrollbar-width: none;
 `,[j("&::-webkit-scrollbar, &::-webkit-scrollbar-track-piece, &::-webkit-scrollbar-thumb",`
 width: 0;
 height: 0;
 display: none;
 `)]),j("&::before, &::after",`
 transition: box-shadow .3s var(--n-bezier);
 pointer-events: none;
 content: "";
 position: absolute;
 z-index: 1;
 `),j("&.transition-disabled",[j("&::before, &::after",`
 transition: none;
 `)])]),l("tabs-nav-scroll-content",`
 display: flex;
 position: relative;
 min-width: 100%;
 min-height: 100%;
 width: fit-content;
 box-sizing: border-box;
 `),l("tabs-wrapper",`
 display: inline-flex;
 flex-wrap: nowrap;
 position: relative;
 `),l("tabs-tab-wrapper",`
 display: flex;
 flex-wrap: nowrap;
 flex-shrink: 0;
 flex-grow: 0;
 `),l("tabs-tab",`
 cursor: pointer;
 white-space: nowrap;
 flex-wrap: nowrap;
 display: inline-flex;
 align-items: center;
 color: var(--n-tab-text-color);
 font-size: var(--n-tab-font-size);
 background-clip: padding-box;
 padding: var(--n-tab-padding);
 transition:
 box-shadow .3s var(--n-bezier),
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[g("disabled",{cursor:"not-allowed"}),fe("close",`
 margin-inline-start: 6px;
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `),fe("label",`
 display: flex;
 align-items: center;
 z-index: 1;
 `)]),l("tabs-bar",`
 position: absolute;
 bottom: 0;
 height: 2px;
 border-radius: 1px;
 background-color: var(--n-bar-color);
 transition:
 left .2s var(--n-bezier),
 max-width .2s var(--n-bezier),
 opacity .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 `,[j("&.transition-disabled",`
 transition: none;
 `),g("disabled",`
 background-color: var(--n-tab-text-color-disabled)
 `)]),l("tabs-pane-wrapper",`
 position: relative;
 overflow: hidden;
 transition: max-height .2s var(--n-bezier);
 `),l("tab-pane",`
 color: var(--n-pane-text-color);
 width: 100%;
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 opacity .2s var(--n-bezier);
 left: 0;
 right: 0;
 top: 0;
 `,[j("&.next-transition-leave-active, &.prev-transition-leave-active, &.next-transition-enter-active, &.prev-transition-enter-active",`
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 transform .2s var(--n-bezier),
 opacity .2s var(--n-bezier);
 `),j("&.next-transition-leave-active, &.prev-transition-leave-active",`
 position: absolute;
 `),j("&.next-transition-enter-from, &.prev-transition-leave-to",`
 transform: translateX(32px);
 opacity: 0;
 `),j("&.next-transition-leave-to, &.prev-transition-enter-from",`
 transform: translateX(-32px);
 opacity: 0;
 `),j("&.next-transition-leave-from, &.next-transition-enter-to, &.prev-transition-leave-from, &.prev-transition-enter-to",`
 transform: translateX(0);
 opacity: 1;
 `)]),l("tabs-tab-pad",`
 box-sizing: border-box;
 width: var(--n-tab-gap);
 flex-grow: 0;
 flex-shrink: 0;
 `),g("line-type, bar-type",[l("tabs-tab",`
 font-weight: var(--n-tab-font-weight);
 box-sizing: border-box;
 vertical-align: bottom;
 `,[j("&:hover",{color:"var(--n-tab-text-color-hover)"}),g("active",`
 color: var(--n-tab-text-color-active);
 font-weight: var(--n-tab-font-weight-active);
 `),g("disabled",{color:"var(--n-tab-text-color-disabled)"})])]),l("tabs-nav",[fe("prefix, suffix",`
 border-color: var(--n-tab-border-color);
 `),l("tabs-nav-scroll-content",`
 border-color: var(--n-tab-border-color);
 `),g("line-type",[g("top",[fe("prefix, suffix",`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),l("tabs-nav-scroll-content",`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),l("tabs-bar",`
 bottom: -1px;
 `)]),g("left",[fe("prefix, suffix",`
 border-right: 1px solid var(--n-tab-border-color);
 `),l("tabs-nav-scroll-content",`
 border-right: 1px solid var(--n-tab-border-color);
 `),l("tabs-bar",`
 right: -1px;
 `)]),g("right",[fe("prefix, suffix",`
 border-left: 1px solid var(--n-tab-border-color);
 `),l("tabs-nav-scroll-content",`
 border-left: 1px solid var(--n-tab-border-color);
 `),l("tabs-bar",`
 left: -1px;
 `)]),g("bottom",[fe("prefix, suffix",`
 border-top: 1px solid var(--n-tab-border-color);
 `),l("tabs-nav-scroll-content",`
 border-top: 1px solid var(--n-tab-border-color);
 `),l("tabs-bar",`
 top: -1px;
 `)]),fe("prefix, suffix",`
 transition: border-color .3s var(--n-bezier);
 `),l("tabs-nav-scroll-content",`
 transition: border-color .3s var(--n-bezier);
 `),l("tabs-bar",`
 border-radius: 0;
 `)]),g("card-type",[fe("prefix, suffix",`
 transition: border-color .3s var(--n-bezier);
 `),l("tabs-pad",`
 flex-grow: 1;
 transition: border-color .3s var(--n-bezier);
 `),l("tabs-tab-pad",`
 transition: border-color .3s var(--n-bezier);
 `),l("tabs-tab",`
 font-weight: var(--n-tab-font-weight);
 border: 1px solid var(--n-tab-border-color);
 background-color: var(--n-tab-color);
 box-sizing: border-box;
 position: relative;
 vertical-align: bottom;
 display: flex;
 justify-content: space-between;
 font-size: var(--n-tab-font-size);
 color: var(--n-tab-text-color);
 `,[g("addable",`
 padding-left: 8px;
 padding-right: 8px;
 font-size: 16px;
 justify-content: center;
 `,[fe("height-placeholder",`
 width: 0;
 font-size: var(--n-tab-font-size);
 `),kn("disabled",[j("&:hover",`
 color: var(--n-tab-text-color-hover);
 `)])]),g("closable","padding-inline-end: 8px;"),g("active",`
 background-color: #0000;
 font-weight: var(--n-tab-font-weight-active);
 color: var(--n-tab-text-color-active);
 `),g("disabled","color: var(--n-tab-text-color-disabled);")])]),g("left, right",`
 flex-direction: column; 
 `,[fe("prefix, suffix",`
 padding: var(--n-tab-padding-vertical);
 `),l("tabs-wrapper",`
 flex-direction: column;
 `),l("tabs-tab-wrapper",`
 flex-direction: column;
 `,[l("tabs-tab-pad",`
 height: var(--n-tab-gap-vertical);
 width: 100%;
 `)])]),g("top",[g("card-type",[l("tabs-scroll-padding","border-bottom: 1px solid var(--n-tab-border-color);"),fe("prefix, suffix",`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),l("tabs-tab",`
 border-top-left-radius: var(--n-tab-border-radius);
 border-top-right-radius: var(--n-tab-border-radius);
 `,[g("active",`
 border-bottom: 1px solid #0000;
 `)]),l("tabs-tab-pad",`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),l("tabs-pad",`
 border-bottom: 1px solid var(--n-tab-border-color);
 `)])]),g("left",[g("card-type",[l("tabs-scroll-padding","border-right: 1px solid var(--n-tab-border-color);"),fe("prefix, suffix",`
 border-right: 1px solid var(--n-tab-border-color);
 `),l("tabs-tab",`
 border-top-left-radius: var(--n-tab-border-radius);
 border-bottom-left-radius: var(--n-tab-border-radius);
 `,[g("active",`
 border-right: 1px solid #0000;
 `)]),l("tabs-tab-pad",`
 border-right: 1px solid var(--n-tab-border-color);
 `),l("tabs-pad",`
 border-right: 1px solid var(--n-tab-border-color);
 `)])]),g("right",[g("card-type",[l("tabs-scroll-padding","border-left: 1px solid var(--n-tab-border-color);"),fe("prefix, suffix",`
 border-left: 1px solid var(--n-tab-border-color);
 `),l("tabs-tab",`
 border-top-right-radius: var(--n-tab-border-radius);
 border-bottom-right-radius: var(--n-tab-border-radius);
 `,[g("active",`
 border-left: 1px solid #0000;
 `)]),l("tabs-tab-pad",`
 border-left: 1px solid var(--n-tab-border-color);
 `),l("tabs-pad",`
 border-left: 1px solid var(--n-tab-border-color);
 `)])]),g("bottom",[g("card-type",[l("tabs-scroll-padding","border-top: 1px solid var(--n-tab-border-color);"),fe("prefix, suffix",`
 border-top: 1px solid var(--n-tab-border-color);
 `),l("tabs-tab",`
 border-bottom-left-radius: var(--n-tab-border-radius);
 border-bottom-right-radius: var(--n-tab-border-radius);
 `,[g("active",`
 border-top: 1px solid #0000;
 `)]),l("tabs-tab-pad",`
 border-top: 1px solid var(--n-tab-border-color);
 `),l("tabs-pad",`
 border-top: 1px solid var(--n-tab-border-color);
 `)])])]),l("tabs-scroll-button",[g("start",`
 padding-left: 10px;
 padding-right: 6px;
 `),g("end",`
 padding-right: 10px;
 padding-left: 6px;
 `),g("up",`
 padding-bottom: 10px;
 `),g("down",`
 padding-top: 10px;
 `)])]),_t=Ee({name:"TabsButton",props:{type:{type:String,default:"next"},mergedClsPrefix:{type:String,required:!0},vertical:Boolean,disabled:Boolean,rtl:Boolean,theme:Object,themeOverrides:Object,onClick:Function},setup(e){return{handleClick:()=>{var f;e.disabled||(f=e.onClick)==null||f.call(e,e.type)}}},render(){const{mergedClsPrefix:e,disabled:o,type:f,vertical:w,rtl:p,theme:_,themeOverrides:S,handleClick:y}=this,C=f==="next",b=w?C:p?!C:C;return i(),P(We,{text:!0,disabled:o,size:"small",theme:_,themeOverrides:S,onClick:y,class:E([`${e}-tabs-scroll-button`,!w&&f==="prev"&&`${e}-tabs-scroll-button--start`,!w&&f==="next"&&`${e}-tabs-scroll-button--end`,w&&f==="prev"&&`${e}-tabs-scroll-button--up`,w&&f==="next"&&`${e}-tabs-scroll-button--down`])},{icon:()=>(i(),P(Ze,{clsPrefix:e,style:Fe(w?{transform:"rotate(90deg)"}:void 0)},{default:()=>b?(i(),P(Kn,{key:1})):(i(),P(Gn,{key:2}))},1032,["clsPrefix","style"]))},1032,["disabled","theme","themeOverrides","onClick","class"])}});const dt=la,Ca={...tt.props,value:[String,Number],defaultValue:[String,Number],trigger:{type:String,default:"click"},type:{type:String,default:"bar"},closable:Boolean,justifyContent:String,size:String,placement:{type:String,default:"top"},tabStyle:[String,Object],tabClass:String,addTabStyle:[String,Object],addTabClass:String,barWidth:Number,paneClass:String,paneStyle:[String,Object],paneWrapperClass:String,paneWrapperStyle:[String,Object],addable:[Boolean,Object],tabsPadding:{type:Number,default:0},animated:Boolean,onBeforeLeave:Function,onAdd:Function,"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],onClose:[Function,Array],labelSize:String,activeName:[String,Number],onActiveNameChange:[Function,Array],showScrollButton:Boolean,centerActiveTab:Boolean};var ka=Ee({name:"Tabs",props:Ca,slots:Object,setup(e,{slots:o}){var Ue,bt;const{mergedClsPrefixRef:f,inlineThemeDisabled:w,mergedComponentPropsRef:p,mergedRtlRef:_}=Ot(e),S=Bt("Tabs",_,f),y=Ie(()=>{const{placement:t}=e;return t==="start"?S!=null&&S.value?"right":"left":t==="end"?S!=null&&S.value?"left":"right":t}),C=tt("Tabs","-tabs",Sa,Rn,e,f),b=I(null),D=I(null),O=I(null),Y=I(null),te=I(null),G=I(null),U=I(null),M=I(!0),L=I(!0),me=yt(e,["labelSize","size"]),Te=Ie(()=>{var a,u;if(me.value)return me.value;const t=(u=(a=p==null?void 0:p.value)==null?void 0:a.Tabs)==null?void 0:u.size;return t||"medium"}),ge=yt(e,["activeName","value"]),oe=I(ge.value??e.defaultValue??(o.default?(bt=(Ue=nt(o.default())[0])==null?void 0:Ue.props)==null?void 0:bt.name:null)),$=Nt(ge,oe),K={id:0},k=Ie(()=>{if(!(!e.justifyContent||e.type==="card"))return{display:"flex",justifyContent:e.justifyContent}});Ne($,()=>{K.id=0,X(),He(()=>{Ve()})});function q(){var a;const{value:t}=$;return t===null?null:(a=b.value)==null?void 0:a.querySelector(`[data-name="${t}"]`)}function be(t){if(e.type==="card")return;const{value:a}=O;if(!a)return;const u=a.style.opacity==="0";if(t){const x=`${f.value}-tabs-bar--disabled`,{barWidth:F}=e,ee=y.value;if(t.dataset.disabled==="true"?a.classList.add(x):a.classList.remove(x),["top","bottom"].includes(ee)){if(B(["top","maxHeight","height"]),typeof F=="number"&&t.offsetWidth>=F){const H=Math.floor((t.offsetWidth-F)/2)+t.offsetLeft;a.style.left=`${H}px`,a.style.maxWidth=`${F}px`}else a.style.left=`${t.offsetLeft}px`,a.style.maxWidth=`${t.offsetWidth}px`;a.style.width="8192px",u&&(a.style.transition="none"),a.offsetWidth,u&&(a.style.transition="",a.style.opacity="1")}else{if(B(["left","maxWidth","width"]),typeof F=="number"&&t.offsetHeight>=F){const H=Math.floor((t.offsetHeight-F)/2)+t.offsetTop;a.style.top=`${H}px`,a.style.maxHeight=`${F}px`}else a.style.top=`${t.offsetTop}px`,a.style.maxHeight=`${t.offsetHeight}px`;a.style.height="8192px",u&&(a.style.transition="none"),a.offsetHeight,u&&(a.style.transition="",a.style.opacity="1")}}}function ye(){if(e.type==="card")return;const{value:t}=O;t&&(t.style.opacity="0")}function B(t){const{value:a}=O;if(a)for(const u of t)a.style[u]=""}function X(){if(e.type==="card")return;const t=q();t?be(t):ye()}function ve(t,a,u,x){const F=t.getBoundingClientRect(),ee=a.getBoundingClientRect(),H=u?"left":"top",pe=u?"right":"bottom";let Re=0;x?Re=(ee[H]+ee[pe])/2-(F[H]+F[pe])/2:ee[H]<F[H]?Re=ee[H]-F[H]:ee[pe]>F[pe]&&(Re=ee[pe]-F[pe]),Re!==0&&t.scrollBy({[H]:Re,behavior:"smooth"})}function Ve(){var u;const t=["top","bottom"].includes(y.value),a=q();if(a)if(t){const x=(u=G.value)==null?void 0:u.$el;if(!x)return;ve(x,a,t,e.centerActiveTab)}else{const{value:x}=U;if(!x)return;ve(x,a,t,e.centerActiveTab)}}const xe=I(null);let Se=0,Ce=null;function Je(t){const a=xe.value;if(a){Se=t.getBoundingClientRect().height;const u=`${Se}px`,x=()=>{a.style.height=u,a.style.maxHeight=u};Ce?(x(),Ce(),Ce=null):Ce=x}}function je(t){const a=xe.value;if(a){const u=t.getBoundingClientRect().height,x=()=>{document.body.offsetHeight,a.style.maxHeight=`${u}px`,a.style.height=`${Math.max(Se,u)}px`};Ce?(Ce(),Ce=null,x()):Ce=x}}function De(){const t=xe.value;if(t){t.style.maxHeight="",t.style.height="";const{paneWrapperStyle:a}=e;if(typeof a=="string")t.style.cssText=a;else if(a){const{maxHeight:u,height:x}=a;u!==void 0&&(t.style.maxHeight=u),x!==void 0&&(t.style.height=x)}}}const s={value:[]},n=I("next");function c(t){const a=$.value;let u="next";for(const x of s.value){if(x===a)break;if(x===t){u="prev";break}}n.value=u,h(t)}function h(t){const{onActiveNameChange:a,onUpdateValue:u,"onUpdate:value":x}=e;a&&Ae(a,t),u&&Ae(u,t),x&&Ae(x,t),oe.value=t}function R(t){const{onClose:a}=e;a&&Ae(a,t)}function m(t){if(["top","bottom"].includes(y.value)){const{value:a}=G;if(!a)return;const u=a.$el;if(!u)return;const x=u.offsetWidth,F=!!(S!=null&&S.value),ee=t==="next"?x:-x;u.scrollBy({left:F?-ee:ee,behavior:"smooth"})}else{const{value:a}=U;if(!a)return;const u=a.offsetHeight,x=t==="next"?a.scrollTop+u:a.scrollTop-u;a.scrollTo({top:x,left:0,behavior:"smooth"})}}let z=!0;function de(){const{value:t}=O;if(!t)return;z&&(z=!1);const a="transition-disabled";t.classList.add(a),X(),t.classList.remove(a)}const Q=I(null);function ke({transitionDisabled:t}){const a=b.value;if(!a)return;t&&a.classList.add("transition-disabled");const u=q();u&&Q.value&&(Q.value.style.width=`${u.offsetWidth}px`,Q.value.style.height=`${u.offsetHeight}px`,Q.value.style.transform=`translate(${u.offsetLeft}px, ${u.offsetTop}px)`,t&&Q.value.offsetWidth),t&&a.classList.remove("transition-disabled")}Ne([$],()=>{e.type==="segment"&&He(()=>{ke({transitionDisabled:!1})})}),Lt(()=>{e.type==="segment"&&ke({transitionDisabled:!0})});let ne=0;function W(t){var u;if(t.contentRect.width===0&&t.contentRect.height===0||ne===t.contentRect.width)return;ne=t.contentRect.width;const{type:a}=e;(a==="line"||a==="bar")&&(z||(u=e.justifyContent)!=null&&u.startsWith("space"))&&de(),a!=="segment"&&ce(ie())}const he=dt(W,64);function V(){const{type:t}=e;t==="line"||t==="bar"?de():t==="segment"&&ke({transitionDisabled:!0})}Ne([()=>e.justifyContent,()=>e.size],()=>{He(()=>{(e.type==="line"||e.type==="bar")&&de()})}),Ne([y,()=>S==null?void 0:S.value],()=>{He(()=>{V(),ce(ie(),{instantly:!0})})}),Ne(()=>e.type,()=>{He(()=>{const t=D.value;t&&(t.classList.add("transition-disabled"),V(),t.offsetWidth,t.classList.remove("transition-disabled"))})});const ae=I(!1);function ue(t){var pe;const{target:a,contentRect:{width:u,height:x}}=t,F=a.parentElement.parentElement.offsetWidth,ee=a.parentElement.parentElement.offsetHeight,H=y.value;if(!ae.value)H==="top"||H==="bottom"?F<u&&(ae.value=!0):ee<x&&(ae.value=!0);else{const{value:Re}=te;if(!Re)return;H==="top"||H==="bottom"?F-u>Re.$el.offsetWidth&&(ae.value=!1):ee-x>Re.$el.offsetHeight&&(ae.value=!1)}ce(((pe=G.value)==null?void 0:pe.$el)||null)}const r=dt(ue,64);function d(){const{onAdd:t}=e;t&&t()}const T=I(!1);function ie(){var a;const t=y.value;return(t==="top"||t==="bottom"?(a=G.value)==null?void 0:a.$el:U.value)||null}function ce(t,a={instantly:!1}){if(!t)return;const u=a.instantly?Y.value:null;u&&u.classList.add("transition-disabled");const x=1,F=y.value;if(F==="top"||F==="bottom"){const{scrollLeft:ee,scrollWidth:H,offsetWidth:pe}=t,Re=Math.abs(ee);M.value=Re<=x,L.value=Re+pe>=H-x,T.value=pe<H-x}else{const{scrollTop:ee,scrollHeight:H,offsetHeight:pe}=t;M.value=ee<=x,L.value=ee+pe>=H-x,T.value=pe<H-x}u&&(u.offsetWidth,u.classList.remove("transition-disabled"))}const we=dt(t=>{ce(t.target)},64);On(ft,{triggerRef:ze(e,"trigger"),tabStyleRef:ze(e,"tabStyle"),tabClassRef:ze(e,"tabClass"),addTabStyleRef:ze(e,"addTabStyle"),addTabClassRef:ze(e,"addTabClass"),paneClassRef:ze(e,"paneClass"),paneStyleRef:ze(e,"paneStyle"),mergedClsPrefixRef:f,typeRef:ze(e,"type"),closableRef:ze(e,"closable"),valueRef:$,tabChangeIdRef:K,onBeforeLeaveRef:ze(e,"onBeforeLeave"),activateTab:c,handleClose:R,handleAdd:d}),Dn(()=>{X(),Ve()}),Tn(()=>{const{value:t}=Y;if(!t)return;const{value:a}=f,u=`${a}-tabs-nav-scroll-wrapper--shadow-start`,x=`${a}-tabs-nav-scroll-wrapper--shadow-end`;M.value?t.classList.remove(u):t.classList.add(u),L.value?t.classList.remove(x):t.classList.add(x)});const Le={syncBarPosition:()=>{X()},scrollToCurrentTab:()=>{Ve()}},Ge=()=>{ke({transitionDisabled:!0})},Pe=Ie(()=>{const{value:t}=Te,{type:a}=e,u=`${t}${{card:"Card",bar:"Bar",line:"Line",segment:"Segment"}[a]}`,{self:{barColor:x,closeIconColor:F,closeIconColorHover:ee,closeIconColorPressed:H,tabColor:pe,tabBorderColor:Re,paneTextColor:jt,tabFontWeight:Mt,tabBorderRadius:Wt,tabFontWeightActive:Ft,colorSegment:Dt,fontWeightStrong:Ut,tabColorSegment:Ht,closeSize:Jt,closeIconSize:Gt,closeColorHover:Kt,closeColorPressed:qt,closeBorderRadius:Xt,[Be("panePadding",t)]:Ke,[Be("tabPadding",u)]:Yt,[Be("tabPaddingVertical",u)]:Qt,[Be("tabGap",u)]:Zt,[Be("tabGap",`${u}Vertical`)]:en,[Be("tabTextColor",a)]:tn,[Be("tabTextColorActive",a)]:nn,[Be("tabTextColorHover",a)]:an,[Be("tabTextColorDisabled",a)]:rn,[Be("tabFontSize",t)]:on},common:{cubicBezierEaseInOut:sn}}=C.value;return{"--n-bezier":sn,"--n-color-segment":Dt,"--n-bar-color":x,"--n-tab-font-size":on,"--n-tab-text-color":tn,"--n-tab-text-color-active":nn,"--n-tab-text-color-disabled":rn,"--n-tab-text-color-hover":an,"--n-pane-text-color":jt,"--n-tab-border-color":Re,"--n-tab-border-radius":Wt,"--n-close-size":Jt,"--n-close-icon-size":Gt,"--n-close-color-hover":Kt,"--n-close-color-pressed":qt,"--n-close-border-radius":Xt,"--n-close-icon-color":F,"--n-close-icon-color-hover":ee,"--n-close-icon-color-pressed":H,"--n-tab-color":pe,"--n-tab-font-weight":Mt,"--n-tab-font-weight-active":Ft,"--n-tab-padding":Yt,"--n-tab-padding-vertical":Qt,"--n-tab-gap":Zt,"--n-tab-gap-vertical":en,"--n-pane-padding-left":qe(Ke,"left"),"--n-pane-padding-right":qe(Ke,"right"),"--n-pane-padding-top":qe(Ke,"top"),"--n-pane-padding-bottom":qe(Ke,"bottom"),"--n-font-weight-strong":Ut,"--n-tab-color-segment":Ht}}),Oe=w?_n("tabs",Ie(()=>`${Te.value[0]}${e.type[0]}`),Pe,e):void 0;return{mergedClsPrefix:f,mergedValue:$,renderedNames:new Set,segmentCapsuleElRef:Q,tabsPaneWrapperRef:xe,tabsElRef:b,selfElRef:D,barElRef:O,addTabInstRef:te,xScrollInstRef:G,scrollWrapperElRef:Y,addTabFixed:ae,tabWrapperStyle:k,handleNavResize:he,mergedSize:Te,handleScroll:we,handleTabsResize:r,cssVars:w?void 0:Pe,themeClass:Oe==null?void 0:Oe.themeClass,animationDirection:n,renderNameListRef:s,yScrollElRef:U,handleSegmentResize:Ge,onAnimationBeforeLeave:Je,onAnimationEnter:je,onAnimationAfterEnter:De,onRender:Oe==null?void 0:Oe.onRender,startReachedRef:M,endReachedRef:L,isOverflow:T,handleButtonClick:m,mergedTheme:C,rtlEnabled:S,mergedPlacement:y,...Le}},render(){const{mergedClsPrefix:e,type:o,mergedPlacement:f,addTabFixed:w,addable:p,mergedSize:_,renderNameListRef:S,onRender:y,paneWrapperClass:C,paneWrapperStyle:b,startReachedRef:D,endReachedRef:O,isOverflow:Y,showScrollButton:te,handleButtonClick:G,mergedTheme:U,rtlEnabled:M,$slots:{default:L,prefix:me,suffix:Te}}=this;y==null||y();const ge=L?nt(L()).filter(B=>B.type.__TAB_PANE__===!0):[],oe=L?nt(L()).filter(B=>B.type.__TAB__===!0):[],$=!oe.length,K=o==="card",k=o==="segment",q=!K&&!k&&this.justifyContent;S.value=[];const be=()=>{const B=(i(),v("div",{style:Fe(this.tabWrapperStyle),class:E(`${e}-tabs-wrapper`)},[q?A(()=>null):(i(),v("div",{key:1,class:E(`${e}-tabs-scroll-padding`),style:Fe(f==="top"||f==="bottom"?{width:`${this.tabsPadding}px`}:{height:`${this.tabsPadding}px`})},null,6)),$?(i(),v(Z,{key:2},[A(()=>ge.map((X,ve)=>(S.value.push(X.props.name),ut((i(),P(ct,et(X.props,{internalCreatedByPane:!0,internalLeftPadded:ve!==0&&(!q||q==="center"||q==="start"||q==="end")}),mt(X.children?{default:X.children.tab}:void 0),1040,["internalLeftPadded"]))))))],64)):(i(),v(Z,{key:3},[A(()=>oe.map((X,ve)=>(S.value.push(X.props.name),ut(ve!==0&&!q?zt(X):X))))],64)),!w&&p&&K?(i(),v(Z,{key:4},[A(()=>Pt(p,($?ge.length:oe.length)!==0))],64)):A(()=>null),q?A(()=>null):(i(),v("div",{key:7,class:E(`${e}-tabs-scroll-padding`),style:Fe({width:`${this.tabsPadding}px`})},null,6)),K?A(()=>null):(i(),v("div",{key:9,ref:"barElRef",class:E(`${e}-tabs-bar`)},null,2))],6));return i(),v("div",{ref:"tabsElRef",class:E(`${e}-tabs-nav-scroll-content`)},[K&&p?(i(),P(at,{key:0,onResize:this.handleTabsResize},{default:()=>B},1032,["onResize"])):(i(),v(Z,{key:1},[A(()=>B)],64)),K?(i(),v("div",{key:2,class:E(`${e}-tabs-pad`)},null,2)):A(()=>null)],2)},ye=k?"top":f;return i(),v("div",{ref:"selfElRef",class:E([`${e}-tabs`,this.themeClass,`${e}-tabs--${o}-type`,`${e}-tabs--${_}-size`,q&&`${e}-tabs--flex`,`${e}-tabs--${ye}`,M&&`${e}-tabs--rtl`]),style:Fe(this.cssVars)},[N("div",{class:E([`${e}-tabs-nav--${o}-type`,`${e}-tabs-nav--${ye}`,`${e}-tabs-nav`])},[A(()=>Qe(me,B=>B&&(i(),v("div",{class:E(`${e}-tabs-nav__prefix`)},[A(()=>B)],2)))),k?(i(),P(at,{key:0,onResize:this.handleSegmentResize},{default:()=>(i(),v("div",{class:E(`${e}-tabs-rail`),ref:"tabsElRef"},[N("div",{class:E(`${e}-tabs-capsule`),ref:"segmentCapsuleElRef"},[N("div",{class:E(`${e}-tabs-wrapper`)},[N("div",{class:E(`${e}-tabs-tab`)},null,2)],2)],2),$?(i(),v(Z,{key:0},[A(()=>ge.map((B,X)=>(S.value.push(B.props.name),i(),P(ct,et(B.props,{internalCreatedByPane:!0,internalLeftPadded:X!==0}),mt(B.children?{default:B.children.tab}:void 0),1040,["internalLeftPadded"]))))],64)):(i(),v(Z,{key:1},[A(()=>oe.map((B,X)=>(S.value.push(B.props.name),X===0?B:zt(B))))],64))],2))},1032,["onResize"])):(i(),v(Z,{key:1},[A(()=>te&&Y&&(i(),P(_t,{mergedClsPrefix:e,type:"prev",vertical:ye==="left"||ye==="right",disabled:D,rtl:!!M,theme:U.peers.Button,themeOverrides:U.peerOverrides.Button,onClick:G},null,8,["mergedClsPrefix","vertical","disabled","rtl","theme","themeOverrides","onClick"]))),(i(),P(at,{onResize:this.handleNavResize},{default:()=>(i(),v("div",{class:E(`${e}-tabs-nav-scroll-wrapper`),ref:"scrollWrapperElRef"},[["top","bottom"].includes(ye)?(i(),P(ua,{key:0,ref:"xScrollInstRef",onScroll:this.handleScroll},{default:be},1032,["onScroll"])):(i(),v("div",{key:1,class:E(`${e}-tabs-nav-y-scroll`),onScroll:this.handleScroll,ref:"yScrollElRef"},[A(()=>be())],42,["onScroll"]))],2))},1032,["onResize"])),A(()=>te&&Y&&(i(),P(_t,{mergedClsPrefix:e,type:"next",vertical:ye==="left"||ye==="right",disabled:O,rtl:!!M,theme:U.peers.Button,themeOverrides:U.peerOverrides.Button,onClick:G},null,8,["mergedClsPrefix","vertical","disabled","rtl","theme","themeOverrides","onClick"])))],64)),w&&p&&K?(i(),v(Z,{key:2},[A(()=>Pt(p,!0))],64)):A(()=>null),A(()=>Qe(Te,B=>B&&(i(),v("div",{class:E(`${e}-tabs-nav__suffix`)},[A(()=>B)],2))))],2),A(()=>$&&(this.animated&&(ye==="top"||ye==="bottom")?(i(),v("div",{key:1,ref:"tabsPaneWrapperRef",style:Fe(b),class:E([`${e}-tabs-pane-wrapper`,C])},[A(()=>$t(ge,this.mergedValue,this.renderedNames,this.onAnimationBeforeLeave,this.onAnimationEnter,this.onAnimationAfterEnter,this.animationDirection))],6)):$t(ge,this.mergedValue,this.renderedNames)))],6)}});function $t(e,o,f,w,p,_,S){const y=[];return e.forEach(C=>{const{name:b,displayDirective:D,"display-directive":O}=C.props,Y=G=>D===G||O===G,te=o===b;if(C.key!==void 0&&(C.key=b),te||Y("show")||Y("show:lazy")&&f.has(b)){f.has(b)||f.add(b);const G=!Y("if");y.push(G?$n(C,[[Pn,te]]):C)}}),S?(i(),P(zn,{name:`${S}-transition`,onBeforeLeave:w,onEnter:p,onAfterEnter:_},{default:()=>y},1032,["name","onBeforeLeave","onEnter","onAfterEnter"])):y}function Pt(e,o){return i(),P(ct,{ref:"addTabInstRef",key:"__addable",name:"__addable",internalCreatedByPane:!0,internalAddable:!0,internalLeftPadded:o,disabled:typeof e=="object"&&e.disabled},null,8,["internalLeftPadded","disabled"])}function zt(e){const o=In(e);return o.props?o.props.internalLeftPadded=!0:o.props={internalLeftPadded:!0},o}function ut(e){return Array.isArray(e.dynamicProps)?e.dynamicProps.includes("internalLeftPadded")||e.dynamicProps.push("internalLeftPadded"):e.dynamicProps=["internalLeftPadded"],e}const Ra={class:"cfg-viewbar"},Ta={class:"cfg-viewhint"},_a={class:"import-title"},$a={key:0,class:"import-list"},Pa={key:1,class:"import-ignored"},za={key:0},Ia={class:"import-actions"},Oa={class:"group-head"},Ba={class:"group-hint"},Aa={class:"group-count"},La={class:"cfg-grid"},Na={class:"cfg-item-head"},Ea={class:"cfg-label"},Va={class:"tip-text"},ja=["title"],Ma={class:"cfg-item-ctl"},Wa={class:"switch-state"},Fa={key:1,class:"group-hint cfg-empty"},Da={class:"actions"},It="humanizer-config-simple",Ua=Ee({__name:"ConfigView",setup(e){const{apiGet:o,apiPost:f}=Vn(),w=Jn(),p=Bn(),_=I(""),S=I(!0),y=I(!1),C=I({}),b=En({}),D=I(""),O=I(null),Y={persona:"表达基调 · 一键预设",style:"表达 · 说话风格与语料",humanize:"表达 · 润色去痕",time:"感知 · 时间与节奏",emotion:"感知 · 情绪惯性",proactive:"主动 · 聊天与追问",typing:"发送 · 延迟分段与防护",growth:"成长档案 · 私聊元数据"},te={persona:"一个旋钮同时决定时间/情绪/主动三域；选「自定义」才完全按细分开关工作",style:"风格档案、语料检索与真人感规则注入",humanize:"本地规则清理 AI 写作痕迹（不调用 LLM）；规则质检开关也在本组",time:"时间感知档位、间隙/节奏/历法/生活状态",emotion:"跨消息的轻微情绪状态与时间衰减",proactive:"主动聊天预设、话题选择与轻追问",typing:"打字延迟、消息分段与防抖防护",growth:"仅私聊按会话与宿主角色隔离；仅保存消息元数据，不保存消息正文；不会按天数自动晋级。日志损坏时只读且不写回。"},G={custom:"自定义（按细分开关）",simple:"简化",standard:"标准",full:"完整",reserved:"克制",clingy:"黏人",natural:"自然",work:"工作"};function U(s){return G[s]||s}const M={custom:"自定义",reserved:"克制",natural:"自然",clingy:"黏人",work:"工作"},L=Ie(()=>{var s;return String(((s=b.persona)==null?void 0:s.preset)||"custom")}),me=Ie(()=>M[L.value]||L.value),Te=Ie(()=>{const s=O.value;if(S.value||!s)return 0;let n=0;for(const c of Object.keys(b)){const h=s[c]||{};for(const R of Object.keys(b[c]))JSON.stringify(h[R])!==JSON.stringify(b[c][R])&&(n+=1)}return n}),ge=Ie(()=>Te.value>0),oe=I(null);function $(){const s={exported_at:new Date().toISOString(),config:JSON.parse(JSON.stringify(b))},n=new Blob([JSON.stringify(s,null,2)],{type:"application/json"}),c=URL.createObjectURL(n),h=document.createElement("a");h.href=c,h.download="humanizer-config.json",h.click(),URL.revokeObjectURL(c)}function K(){var s;(s=oe.value)==null||s.click()}const k=I(null);function q(s,n){const c=s==null?void 0:s.kind;return c==="switch"?typeof n=="boolean"?null:"需要布尔值":c==="number"?typeof n!="number"||!Number.isFinite(n)?"需要数字":s.integer&&!Number.isInteger(n)?"需要整数":typeof s.min=="number"&&n<s.min?`不能小于 ${s.min}`:typeof s.max=="number"&&n>s.max?`不能大于 ${s.max}`:null:c==="select"?typeof n!="string"?"需要字符串选项":n===""||(Array.isArray(s.options)?s.options:[]).some(R=>R.value===n)?null:"不在可选范围内":c==="text"||c==="textarea"?typeof n=="string"?null:"需要字符串":"不支持的类型"}function be(s,n){return Array.isArray(s)?Array.isArray(n)?n.every(c=>typeof c=="string")?null:"列表项必须都是字符串":"需要列表":s!==null&&typeof s=="object"?!n||typeof n!="object"||Array.isArray(n)?"需要对象":null:typeof n==typeof s?null:"类型不符"}function ye(){if(!k.value)return;let s=0;for(const n of k.value.changes)b[n.group][n.key]=n.to,s+=1;k.value=null,w.success(`已应用 ${s} 项配置，确认无误后点击「保存配置」`)}function B(s){var R;const n=s.target,c=(R=n.files)==null?void 0:R[0];if(n.value="",!c)return;const h=new FileReader;h.onload=()=>{try{const m=JSON.parse(String(h.result||"{}")),z=m&&m.config?m.config:m;if(!z||typeof z!="object")throw new Error("文件不是配置对象");const de=[],Q=[];let ke=0;for(const ne of Object.keys(C.value)){const W=z[ne];if(!W||typeof W!="object")continue;const he=C.value[ne].items||{};for(const[V,ae]of Object.entries(he)){if(!(V in W))continue;const ue=W[V],r=q(ae,ue),d=ae.label||V;if(r){Q.push(`${d}（${r}）`);continue}if(JSON.stringify(b[ne][V])===JSON.stringify(ue)){ke+=1;continue}de.push({group:ne,key:V,label:d,from:b[ne][V],to:ue})}for(const V of Object.keys(b[ne]||{})){if(V in he||!(V in W))continue;const ae=b[ne][V],ue=W[V],r=`${V}（复杂项）`,d=be(ae,ue);if(d){Q.push(`${r}（${d}）`);continue}if(JSON.stringify(ae)===JSON.stringify(ue)){ke+=1;continue}de.push({group:ne,key:V,label:r,from:ae,to:ue})}for(const V of Object.keys(W))V in(b[ne]||{})||Q.push(`${ne}.${V}（未知键）`)}for(const ne of Object.keys(z))ne in C.value||Q.push(`${ne}（未知分组）`);if(!de.length&&!Q.length){k.value=null,w.warning("文件与当前配置一致，无需导入");return}k.value={changes:de,ignored:Q,same:ke}}catch(m){k.value=null,w.error(`导入失败：${(m==null?void 0:m.message)||m}`)}},h.readAsText(c,"utf-8")}function X(s){return Object.keys((s==null?void 0:s.items)||{}).length}const ve=I(""),Ve={persona:["preset"],style:["enabled","active_style","active_style_autofallback","enable_retrieval","rules_enable","qc_enable"],humanize:["enabled","remove_emoji"],time:["awareness_mode","enable_gap","gap_threshold_minutes","enable_life"],emotion:["emotion_mode","emotion_enable"],proactive:["proactive_preset","enable_proactive","proactive_quiet_hours","proactive_active_hours"],typing:["enable","delay_min","delay_max","split_enable"],growth:["enabled"]},xe=I(!0);try{xe.value=localStorage.getItem(It)!=="0"}catch{xe.value=!0}Ne(xe,s=>{try{localStorage.setItem(It,s?"1":"0")}catch{}});function Se(s){var m;const n=((m=C.value[s])==null?void 0:m.items)||{},c=ve.value.trim().toLowerCase();if(c){const z={};for(const[de,Q]of Object.entries(n))`${Q.label||""} ${de} ${Q.hint||""}`.toLowerCase().includes(c)&&(z[de]=Q);return z}if(!xe.value)return n;const h=Ve[s]||[],R={};for(const z of h)n[z]&&(R[z]=n[z]);return R}Ne(ve,s=>{if(!s.trim()||Object.keys(Se(_.value)).length)return;const n=Object.keys(C.value).find(c=>Object.keys(Se(c)).length>0);n&&(_.value=n)});function Ce(s,n){return ve.value.trim()?`${n} (${Object.keys(Se(s)).length})`:n}function Je(s,n){var h,R;const c=C.value[s];return((R=(h=c==null?void 0:c.items)==null?void 0:h[n])==null?void 0:R.options)||[]}async function je(){S.value=!0,D.value="";try{const s=await o("config");if(!s||!s.ok)throw new Error(s&&s.error||"配置读取失败");s.degraded&&(D.value=String(s.error||"后端配置不完整"));const n=s.config||{},c=s.schema_meta||{},h=s.options||{};C.value={};for(const m of Object.keys(Y)){const z=n[m]||{},de=c[m]||{};C.value[m]={label:Y[m]||m,hint:te[m]||"",items:{}},b[m]={};const Q=new Set(["awareness_mode","emotion_mode","proactive_preset"]),ke=Object.keys(z),ne=[...ke.filter(W=>Q.has(W)),...ke.filter(W=>!Q.has(W))];for(const W of ne){b[m][W]=z[W];const he=de.items&&de.items[W]||{},V=typeof z[W];let ae=V==="boolean"?"switch":V==="number"?"number":V==="string"&&String(z[W]).length>60?"textarea":V==="string"?"text":"skip";const ue=[...h[`${m}/${W}`]||[]],r=Array.isArray(he.options)?he.options.filter(d=>typeof d=="string"):[];for(const d of r)ue.includes(d)||ue.push(d);if(ue.length){const d=b[m][W];typeof d=="string"&&d&&!ue.includes(d)&&ue.unshift(d),ae="select"}ae!=="skip"&&(C.value[m].items[W]={kind:ae,integer:he.type==="int",label:he.description||W,hint:he.hint||"",min:typeof he.min=="number"?he.min:void 0,max:typeof he.max=="number"?he.max:void 0,options:ae==="select"?ue.map(d=>({label:U(d),value:d})):[]})}}const R=String(p.query.group||"");_.value=R&&C.value[R]?R:Object.keys(C.value)[0]||"",O.value=JSON.parse(JSON.stringify(b))}catch(s){D.value=(s==null?void 0:s.message)||String(s),w.error("配置读取失败: "+s.message)}finally{S.value=!1}}async function De(){y.value=!0;try{const s={};for(const c of Object.keys(b))s[c]=JSON.parse(JSON.stringify(b[c]));const n=await f("config/save",s);if(n&&n.ok)w.success("配置已保存"),await je();else{const c=n!=null&&n.errors?Object.entries(n.errors).slice(0,3).map(([h,R])=>`${h}: ${R}`).join("；"):"";w.error("保存失败: "+(n&&n.error||"未知错误")+(c?`（${c}）`:""))}}catch(s){w.error("保存失败: "+s.message)}finally{y.value=!1}}return Lt(je),(s,n)=>(i(),P(J(Mn),{show:S.value},{default:se(()=>[S.value?_e("",!0):(i(),v(Z,{key:0},[D.value?(i(),P(J(ot),{key:0,type:"error",bordered:!1,class:"mb-4"},{default:se(()=>[re(" 配置读取失败："+le(D.value)+"。当前显示为空表单，请检查后端日志或重载插件后再试（已禁用保存，避免用不完整表单覆盖配置）。 ",1)]),_:1})):_e("",!0),$e(J(Xe),{value:ve.value,"onUpdate:value":n[0]||(n[0]=c=>ve.value=c),clearable:"",placeholder:"搜索配置项：标签 / 键名 / 说明",class:"cfg-search"},null,8,["value"]),N("div",Ra,[N("span",Ta,le(xe.value?"简单视图：只显示每个分组的常用旋钮；搜索始终覆盖全部配置项":"专家视图：显示全部配置项"),1),$e(J(wt),{value:xe.value,"onUpdate:value":n[1]||(n[1]=c=>xe.value=c),size:"small"},{checked:se(()=>[...n[4]||(n[4]=[re("简单",-1)])]),unchecked:se(()=>[...n[5]||(n[5]=[re("专家",-1)])]),_:1},8,["value"])]),k.value?(i(),P(J(ot),{key:1,type:"info",bordered:!1,class:"import-preview"},{default:se(()=>[N("div",_a,[n[8]||(n[8]=re(" 导入预览：将修改 ",-1)),N("b",null,le(k.value.changes.length),1),n[9]||(n[9]=re(" 项",-1)),k.value.ignored.length?(i(),v(Z,{key:0},[n[6]||(n[6]=re("，忽略 ",-1)),N("b",null,le(k.value.ignored.length),1),n[7]||(n[7]=re(" 项",-1))],64)):_e("",!0),k.value.same?(i(),v(Z,{key:1},[re("（"+le(k.value.same)+" 项无变化）",1)],64)):_e("",!0)]),k.value.changes.length?(i(),v("ul",$a,[(i(!0),v(Z,null,rt(k.value.changes.slice(0,5),c=>(i(),v("li",{key:c.group+"."+c.key},le(c.label)+"："+le(String(c.from))+" → "+le(String(c.to)),1))),128))])):_e("",!0),k.value.ignored.length?(i(),v("p",Pa,[re(" 忽略示例："+le(k.value.ignored.slice(0,3).join("；")),1),k.value.ignored.length>3?(i(),v("span",za," …")):_e("",!0)])):_e("",!0),N("div",Ia,[$e(J(We),{size:"small",type:"primary",disabled:!k.value.changes.length,onClick:ye},{default:se(()=>[...n[10]||(n[10]=[re(" 应用导入 ",-1)])]),_:1},8,["disabled"]),$e(J(We),{size:"small",tertiary:"",onClick:n[2]||(n[2]=c=>k.value=null)},{default:se(()=>[...n[11]||(n[11]=[re("取消",-1)])]),_:1})])]),_:1})):_e("",!0),$e(J(An),{class:"cfg-card","content-style":"padding: 6px 20px 22px;"},{default:se(()=>[$e(J(ka),{value:_.value,"onUpdate:value":n[3]||(n[3]=c=>_.value=c),type:"line",animated:""},{default:se(()=>[(i(!0),v(Z,null,rt(C.value,(c,h)=>(i(),P(J(ya),{key:h,name:h,tab:Ce(h,c.label)},{default:se(()=>[h==="persona"&&L.value!=="custom"?(i(),P(J(ot),{key:0,type:"info",bordered:!1,class:"persona-note"},{default:se(()=>[re(" 当前「"+le(me.value)+"」表达基调统一控制时间 / 情绪 / 主动三域。下方各组细分开关与域档位仍会保留，但暂不生效；切回「自定义」即可按细分开关工作。 ",1)]),_:1})):_e("",!0),N("div",Oa,[N("p",Ba,le(c.hint),1),N("span",Aa,[re(le(Object.keys(Se(h)).length)+" / "+le(X(c))+" 项",1),xe.value&&!ve.value.trim()?(i(),v(Z,{key:0},[re("（简单视图）")],64)):_e("",!0)])]),N("div",La,[(i(!0),v(Z,null,rt(Se(h),(R,m)=>(i(),v("div",{key:m,class:Ln(["cfg-item",{wide:R.kind==="textarea"}])},[N("div",Na,[N("span",Ea,le(R.label||m),1),R.hint?(i(),P(J(Hn),{key:0,trigger:"hover",placement:"top-start",style:{"max-width":"420px"}},{trigger:se(()=>[$e(J(Nn),{icon:"lucide:circle-help",class:"lbl-info"})]),default:se(()=>[N("span",Va,le(R.hint),1)]),_:2},1024)):_e("",!0),N("span",{class:"cfg-key",title:m},le(m),9,ja)]),N("div",Ma,[R.kind==="switch"?(i(),v(Z,{key:0},[$e(J(wt),{value:b[h][m],"onUpdate:value":z=>b[h][m]=z},null,8,["value","onUpdate:value"]),N("span",Wa,le(b[h][m]?"已开启":"已关闭"),1)],64)):R.kind==="number"?(i(),P(J(ga),{key:1,value:b[h][m],"onUpdate:value":z=>b[h][m]=z,min:R.min,max:R.max,precision:R.integer?0:void 0,class:"ctl-number"},null,8,["value","onUpdate:value","min","max","precision"])):R.kind==="select"?(i(),P(J(Un),{key:2,value:b[h][m],"onUpdate:value":z=>b[h][m]=z,options:Je(h,m),clearable:"",filterable:"",placeholder:"默认 / 自动"},null,8,["value","onUpdate:value","options"])):R.kind==="textarea"?(i(),P(J(Xe),{key:3,value:b[h][m],"onUpdate:value":z=>b[h][m]=z,type:"textarea",autosize:{minRows:3,maxRows:8}},null,8,["value","onUpdate:value"])):(i(),P(J(Xe),{key:4,value:b[h][m],"onUpdate:value":z=>b[h][m]=z,placeholder:""},null,8,["value","onUpdate:value"]))])],2))),128))]),Object.keys(Se(h)).length?_e("",!0):(i(),v("p",Fa," 没有匹配「"+le(ve.value)+"」的配置项。 ",1))]),_:2},1032,["name","tab"]))),128))]),_:1},8,["value"])]),_:1}),N("div",Da,[ge.value?(i(),P(J(gt),{key:0,type:"warning",round:"",size:"small"},{default:se(()=>[re(" 有 "+le(Te.value)+" 项未保存修改 ",1)]),_:1})):(i(),P(J(gt),{key:1,type:"success",round:"",size:"small"},{default:se(()=>[...n[12]||(n[12]=[re("配置已是最新",-1)])]),_:1})),n[17]||(n[17]=N("span",{class:"actions-spacer"},null,-1)),$e(J(We),{tertiary:"",onClick:$},{default:se(()=>[...n[13]||(n[13]=[re("导出配置",-1)])]),_:1}),$e(J(We),{tertiary:"",onClick:K},{default:se(()=>[...n[14]||(n[14]=[re("导入配置",-1)])]),_:1}),N("input",{ref_key:"importInput",ref:oe,type:"file",accept:"application/json,.json",class:"hidden-file",onChange:B},null,544),$e(J(We),{tertiary:"",onClick:je},{default:se(()=>[...n[15]||(n[15]=[re("放弃修改",-1)])]),_:1}),$e(J(We),{type:"primary",loading:y.value,disabled:!ge.value||!!D.value,onClick:De},{default:se(()=>[...n[16]||(n[16]=[re(" 保存配置 ",-1)])]),_:1},8,["loading","disabled"])])],64))]),_:1},8,["show"]))}}),nr=jn(Ua,[["__scopeId","data-v-a6c03644"]]);export{nr as default};
