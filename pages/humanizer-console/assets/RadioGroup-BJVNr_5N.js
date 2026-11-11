import{J as B,a6 as x,a7 as c,H as R,a8 as j,a1 as le,M as O,N as W,h as V,O as L,R as I,a0 as ce,$ as K,d as H,K as P,z as ue,o as D,c as E,a as N,V as T,L as _,n as J,bC as Q,Q as Y,ad as q,e as U,U as be,ag as A,g as he,a9 as fe,al as ve}from"./index-k2JXiZDX.js";import{g as ge}from"./get-slot-VaplJ9hC.js";import{b as X}from"./Select-6MhKkqZw.js";var pe=B("radio",`
 line-height: var(--n-label-line-height);
 outline: none;
 position: relative;
 user-select: none;
 -webkit-user-select: none;
 display: inline-flex;
 align-items: flex-start;
 flex-wrap: nowrap;
 font-size: var(--n-font-size);
 word-break: break-word;
`,[x("checked",[c("dot",`
 background-color: var(--n-color-active);
 `)]),c("dot-wrapper",`
 position: relative;
 flex-shrink: 0;
 flex-grow: 0;
 width: var(--n-radio-size);
 `),B("radio-input",`
 position: absolute;
 border: 0;
 width: 0;
 height: 0;
 opacity: 0;
 margin: 0;
 `),c("dot",`
 position: absolute;
 top: 50%;
 left: 0;
 transform: translateY(-50%);
 height: var(--n-radio-size);
 width: var(--n-radio-size);
 background: var(--n-color);
 box-shadow: var(--n-box-shadow);
 border-radius: 50%;
 transition:
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 `,[R("&::before",`
 content: "";
 opacity: 0;
 position: absolute;
 left: 4px;
 top: 4px;
 height: calc(100% - 8px);
 width: calc(100% - 8px);
 border-radius: 50%;
 transform: scale(.8);
 background: var(--n-dot-color-active);
 transition: 
 opacity .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 transform .3s var(--n-bezier);
 `),x("checked",{boxShadow:"var(--n-box-shadow-active)"},[R("&::before",`
 opacity: 1;
 transform: scale(1);
 `)])]),c("label",`
 color: var(--n-text-color);
 padding: var(--n-label-padding);
 font-weight: var(--n-label-font-weight);
 display: inline-block;
 transition: color .3s var(--n-bezier);
 `),j("disabled",`
 cursor: pointer;
 `,[R("&:hover",[c("dot",{boxShadow:"var(--n-box-shadow-hover)"})]),x("focus",[R("&:not(:active)",[c("dot",{boxShadow:"var(--n-box-shadow-focus)"})])])]),x("disabled",`
 cursor: not-allowed;
 `,[c("dot",{boxShadow:"var(--n-box-shadow-disabled)",backgroundColor:"var(--n-color-disabled)"},[R("&::before",{backgroundColor:"var(--n-dot-color-disabled)"}),x("checked",`
 opacity: 1;
 `)]),c("label",{color:"var(--n-text-color-disabled)"}),B("radio-input",`
 cursor: not-allowed;
 `)])]);const me={name:String,value:{type:[String,Number,Boolean],default:"on"},checked:{type:Boolean,default:void 0},defaultChecked:Boolean,disabled:{type:Boolean,default:void 0},label:String,size:String,onUpdateChecked:[Function,Array],"onUpdate:checked":[Function,Array],checkedValue:{type:Boolean,default:void 0}},Z=ce("n-radio-group");function xe(o){const e=le(Z,null),{mergedClsPrefixRef:n,mergedComponentPropsRef:r}=O(o),s=W(o,{mergedSize(t){var m,F;const{size:a}=o;if(a!==void 0)return a;if(e){const{mergedSizeRef:{value:$}}=e;if($!==void 0)return $}if(t)return t.mergedSize.value;const d=(F=(m=r==null?void 0:r.value)==null?void 0:m.Radio)==null?void 0:F.size;return d||"medium"},mergedDisabled(t){return!!(o.disabled||e!=null&&e.disabledRef.value||t!=null&&t.disabled.value)}}),{mergedSizeRef:b,mergedDisabledRef:h}=s,l=V(null),i=V(null),u=V(o.defaultChecked),v=K(o,"checked"),f=X(v,u),g=L(()=>e?e.valueRef.value===o.value:f.value),k=L(()=>{const{name:t}=o;if(t!==void 0)return t;if(e)return e.nameRef.value}),p=V(!1);function z(){if(e){const{doUpdateValue:t}=e,{value:a}=o;I(t,a)}else{const{onUpdateChecked:t,"onUpdate:checked":a}=o,{nTriggerFormInput:d,nTriggerFormChange:m}=s;t&&I(t,!0),a&&I(a,!0),d(),m(),u.value=!0}}function C(){h.value||g.value||z()}function S(){C(),l.value&&(l.value.checked=g.value)}function y(){p.value=!1}function w(){p.value=!0}return{mergedClsPrefix:e?e.mergedClsPrefixRef:n,inputRef:l,labelRef:i,mergedName:k,mergedDisabled:h,renderSafeChecked:g,focus:p,mergedSize:b,handleRadioInputChange:S,handleRadioInputBlur:y,handleRadioInputFocus:w}}const Re=["value","name","checked","disabled","onChange","onFocus","onBlur"],ke={...P.props,...me};var we=H({name:"Radio",props:ke,setup(o){const e=xe(o),n=P("Radio","-radio",pe,Q,o,e.mergedClsPrefix),r=U(()=>{const{mergedSize:{value:u}}=e,{common:{cubicBezierEaseInOut:v},self:{boxShadow:f,boxShadowActive:g,boxShadowDisabled:k,boxShadowFocus:p,boxShadowHover:z,color:C,colorDisabled:S,colorActive:y,textColor:w,textColorDisabled:t,dotColorActive:a,dotColorDisabled:d,labelPadding:m,labelLineHeight:F,labelFontWeight:$,[A("fontSize",u)]:G,[A("radioSize",u)]:M}}=n.value;return{"--n-bezier":v,"--n-label-line-height":F,"--n-label-font-weight":$,"--n-box-shadow":f,"--n-box-shadow-active":g,"--n-box-shadow-disabled":k,"--n-box-shadow-focus":p,"--n-box-shadow-hover":z,"--n-color":C,"--n-color-active":y,"--n-color-disabled":S,"--n-dot-color-active":a,"--n-dot-color-disabled":d,"--n-font-size":G,"--n-radio-size":M,"--n-text-color":w,"--n-text-color-disabled":t,"--n-label-padding":m}}),{inlineThemeDisabled:s,mergedClsPrefixRef:b,mergedRtlRef:h}=O(o),l=Y("Radio",h,b),i=s?q("radio",U(()=>e.mergedSize.value[0]),r,o):void 0;return Object.assign(e,{rtlEnabled:l,cssVars:s?void 0:r,themeClass:i==null?void 0:i.themeClass,onRender:i==null?void 0:i.onRender})},render(){const{$slots:o,mergedClsPrefix:e,onRender:n,label:r}=this;return n==null||n(),(()=>{const s=ue("f8c6901d8cd45c02");return D(),E("label",{class:_([`${e}-radio`,this.themeClass,this.rtlEnabled&&`${e}-radio--rtl`,this.mergedDisabled&&`${e}-radio--disabled`,this.renderSafeChecked&&`${e}-radio--checked`,this.focus&&`${e}-radio--focus`]),style:J(this.cssVars)},[N("div",{class:_(`${e}-radio__dot-wrapper`)},[s[0]||(s[0]=T(" ",-1)),N("div",{class:_([`${e}-radio__dot`,this.renderSafeChecked&&`${e}-radio__dot--checked`])},null,2),N("input",{ref:"inputRef",type:"radio",class:_(`${e}-radio-input`),value:this.value,name:this.mergedName,checked:this.renderSafeChecked,disabled:this.mergedDisabled,onChange:this.handleRadioInputChange,onFocus:this.handleRadioInputFocus,onBlur:this.handleRadioInputBlur},null,42,Re)],2),T(()=>be(o.default,b=>!b&&!r?null:(D(),E("div",{ref:"labelRef",class:_(`${e}-radio__label`)},[T(()=>b||r)],2))))],6)})()}}),ze=B("radio-group",`
 display: inline-block;
 font-size: var(--n-font-size);
`,[c("splitor",`
 display: inline-block;
 vertical-align: bottom;
 width: 1px;
 transition:
 background-color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 background: var(--n-button-border-color);
 `,[x("checked",{backgroundColor:"var(--n-button-border-color-active)"}),x("disabled",{opacity:"var(--n-opacity-disabled)"})]),x("button-group",`
 white-space: nowrap;
 height: var(--n-height);
 line-height: var(--n-height);
 `,[B("radio-button",{height:"var(--n-height)",lineHeight:"var(--n-height)"}),c("splitor",{height:"var(--n-height)"})]),B("radio-button",`
 vertical-align: bottom;
 outline: none;
 position: relative;
 user-select: none;
 -webkit-user-select: none;
 display: inline-block;
 box-sizing: border-box;
 padding-left: 14px;
 padding-right: 14px;
 white-space: nowrap;
 transition:
 background-color .3s var(--n-bezier),
 opacity .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 background: var(--n-button-color);
 color: var(--n-button-text-color);
 border-top: 1px solid var(--n-button-border-color);
 border-bottom: 1px solid var(--n-button-border-color);
 `,[B("radio-input",`
 pointer-events: none;
 position: absolute;
 border: 0;
 border-radius: inherit;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 opacity: 0;
 z-index: 1;
 `),c("state-border",`
 z-index: 1;
 pointer-events: none;
 position: absolute;
 box-shadow: var(--n-button-box-shadow);
 transition: box-shadow .3s var(--n-bezier);
 left: -1px;
 bottom: -1px;
 right: -1px;
 top: -1px;
 `),R("&:first-child",`
 border-top-left-radius: var(--n-button-border-radius);
 border-bottom-left-radius: var(--n-button-border-radius);
 border-left: 1px solid var(--n-button-border-color);
 `,[c("state-border",`
 border-top-left-radius: var(--n-button-border-radius);
 border-bottom-left-radius: var(--n-button-border-radius);
 `)]),R("&:last-child",`
 border-top-right-radius: var(--n-button-border-radius);
 border-bottom-right-radius: var(--n-button-border-radius);
 border-right: 1px solid var(--n-button-border-color);
 `,[c("state-border",`
 border-top-right-radius: var(--n-button-border-radius);
 border-bottom-right-radius: var(--n-button-border-radius);
 `)]),j("disabled",`
 cursor: pointer;
 `,[R("&:hover",[c("state-border",`
 transition: box-shadow .3s var(--n-bezier);
 box-shadow: var(--n-button-box-shadow-hover);
 `),j("checked",{color:"var(--n-button-text-color-hover)"})]),x("focus",[R("&:not(:active)",[c("state-border",{boxShadow:"var(--n-button-box-shadow-focus)"})])])]),x("checked",`
 background: var(--n-button-color-active);
 color: var(--n-button-text-color-active);
 border-color: var(--n-button-border-color-active);
 `),x("disabled",`
 cursor: not-allowed;
 opacity: var(--n-opacity-disabled);
 `)])]);const Ce=["onFocusin","onFocusout"];function Se(o,e,n){var b;const r=[];let s=!1;for(let h=0;h<o.length;++h){const l=o[h],i=(b=l.type)==null?void 0:b.name;i==="RadioButton"&&(s=!0);const u=l.props;if(i!=="RadioButton"){r.push(l);continue}if(h===0)r.push(l);else{const v=r[r.length-1].props,f=e===v.value,g=v.disabled,k=e===u.value,p=u.disabled,z=(f?2:0)+(g?0:1),C=(k?2:0)+(p?0:1),S={[`${n}-radio-group__splitor--disabled`]:g,[`${n}-radio-group__splitor--checked`]:f},y={[`${n}-radio-group__splitor--disabled`]:p,[`${n}-radio-group__splitor--checked`]:k},w=z<C?y:S;r.push((D(),E("div",{key:1,class:_([`${n}-radio-group__splitor`,w])},null,2)),l)}}return{children:r,isButtonGroup:s}}const ye={...P.props,name:String,options:Array,labelField:{type:String,default:"label"},valueField:{type:String,default:"value"},value:[String,Number,Boolean],defaultValue:{type:[String,Number,Boolean],default:null},size:String,disabled:{type:Boolean,default:void 0},"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array]};var $e=H({name:"RadioGroup",props:ye,setup(o){const e=V(null),{mergedSizeRef:n,mergedDisabledRef:r,nTriggerFormChange:s,nTriggerFormInput:b,nTriggerFormBlur:h,nTriggerFormFocus:l}=W(o),{mergedClsPrefixRef:i,inlineThemeDisabled:u,mergedRtlRef:v}=O(o),f=P("Radio","-radio-group",ze,Q,o,i),g=V(o.defaultValue),k=K(o,"value"),p=X(k,g);function z(a){const{onUpdateValue:d,"onUpdate:value":m}=o;d&&I(d,a),m&&I(m,a),g.value=a,s(),b()}function C(a){const{value:d}=e;d&&(d.contains(a.relatedTarget)||l())}function S(a){const{value:d}=e;d&&(d.contains(a.relatedTarget)||h())}ve(Z,{mergedClsPrefixRef:i,nameRef:K(o,"name"),valueRef:p,disabledRef:r,mergedSizeRef:n,doUpdateValue:z});const y=Y("Radio",v,i),w=U(()=>{const{value:a}=n,{common:{cubicBezierEaseInOut:d},self:{buttonBorderColor:m,buttonBorderColorActive:F,buttonBorderRadius:$,buttonBoxShadow:G,buttonBoxShadowFocus:M,buttonBoxShadowHover:ee,buttonColor:oe,buttonColorActive:te,buttonTextColor:re,buttonTextColorActive:ae,buttonTextColorHover:ne,opacityDisabled:ie,[A("buttonHeight",a)]:de,[A("fontSize",a)]:se}}=f.value;return{"--n-font-size":se,"--n-bezier":d,"--n-button-border-color":m,"--n-button-border-color-active":F,"--n-button-border-radius":$,"--n-button-box-shadow":G,"--n-button-box-shadow-focus":M,"--n-button-box-shadow-hover":ee,"--n-button-color":oe,"--n-button-color-active":te,"--n-button-text-color":re,"--n-button-text-color-hover":ne,"--n-button-text-color-active":ae,"--n-height":de,"--n-opacity-disabled":ie}}),t=u?q("radio-group",U(()=>n.value[0]),w,o):void 0;return{selfElRef:e,rtlEnabled:y,mergedClsPrefix:i,mergedValue:p,handleFocusout:S,handleFocusin:C,cssVars:u?void 0:w,themeClass:t==null?void 0:t.themeClass,onRender:t==null?void 0:t.onRender}},render(){var u;const{mergedValue:o,mergedClsPrefix:e,handleFocusin:n,handleFocusout:r}=this,{options:s,labelField:b,valueField:h}=this.$props,{children:l,isButtonGroup:i}=Se(s?s.map(v=>{const f=v[h];return D(),he(we,{key:typeof f=="boolean"?`__n_${f}`:f,value:f,disabled:v.disabled,label:v[b]},null,8,["value","disabled","label"])}):fe(ge(this)),o,e);return(u=this.onRender)==null||u.call(this),D(),E("div",{onFocusin:n,onFocusout:r,ref:"selfElRef",class:_([`${e}-radio-group`,this.rtlEnabled&&`${e}-radio-group--rtl`,this.themeClass,i&&`${e}-radio-group--button-group`]),style:J(this.cssVars)},[T(()=>l)],46,Ce)}});export{$e as R,we as a,me as r,xe as s};
