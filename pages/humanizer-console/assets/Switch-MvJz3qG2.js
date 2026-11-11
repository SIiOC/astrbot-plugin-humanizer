import{G as ve,b1 as ge,b2 as we,J as X,a7 as a,aR as Y,H as j,a6 as s,a8 as G,d as me,K as Q,b3 as A,o as b,c as C,a as _,V as l,U as k,L as n,g as J,n as q,M as pe,N as ye,h as L,ad as xe,e as D,R as E,b4 as ke,m as Se,aO as Be,ag as S,b5 as I,b6 as c,$ as Ce}from"./index-k2JXiZDX.js";import{b as _e}from"./Select-6MhKkqZw.js";function $e(e){const{primaryColor:d,opacityDisabled:f,borderRadius:i,textColor3:v}=e;return{...ge,iconColor:v,textColor:"white",loadingColor:d,opacityDisabled:f,railColor:"rgba(0, 0, 0, .14)",railColorActive:d,buttonBoxShadow:"0 1px 4px 0 rgba(0, 0, 0, 0.3), inset 0 0 1px 0 rgba(0, 0, 0, 0.05)",buttonColor:"#FFF",railBorderRadiusSmall:i,railBorderRadiusMedium:i,railBorderRadiusLarge:i,buttonBorderRadiusSmall:i,buttonBorderRadiusMedium:i,buttonBorderRadiusLarge:i,boxShadowFocus:`0 0 0 2px ${we(d,{alpha:.2})}`}}const ze={common:ve,self:$e};var Re=X("switch",`
 height: var(--n-height);
 min-width: var(--n-width);
 vertical-align: middle;
 user-select: none;
 -webkit-user-select: none;
 display: inline-flex;
 outline: none;
 justify-content: center;
 align-items: center;
`,[a("children-placeholder",`
 height: var(--n-rail-height);
 display: flex;
 flex-direction: column;
 overflow: hidden;
 pointer-events: none;
 visibility: hidden;
 `),a("rail-placeholder",`
 display: flex;
 flex-wrap: none;
 `),a("button-placeholder",`
 width: calc(1.75 * var(--n-rail-height));
 height: var(--n-rail-height);
 `),X("base-loading",`
 position: absolute;
 top: 50%;
 left: 50%;
 transform: translateX(-50%) translateY(-50%);
 font-size: calc(var(--n-button-width) - 4px);
 color: var(--n-loading-color);
 transition: color .3s var(--n-bezier);
 `,[Y({left:"50%",top:"50%",originalTransform:"translateX(-50%) translateY(-50%)"})]),a("checked, unchecked",`
 transition: color .3s var(--n-bezier);
 color: var(--n-text-color);
 box-sizing: border-box;
 position: absolute;
 white-space: nowrap;
 top: 0;
 bottom: 0;
 display: flex;
 align-items: center;
 line-height: 1;
 `),a("checked",`
 right: 0;
 padding-right: calc(1.25 * var(--n-rail-height) - var(--n-offset));
 `),a("unchecked",`
 left: 0;
 justify-content: flex-end;
 padding-left: calc(1.25 * var(--n-rail-height) - var(--n-offset));
 `),j("&:focus",[a("rail",`
 box-shadow: var(--n-box-shadow-focus);
 `)]),s("round",[a("rail","border-radius: calc(var(--n-rail-height) / 2);",[a("button","border-radius: calc(var(--n-button-height) / 2);")])]),G("disabled",[G("icon",[s("rubber-band",[s("pressed",[a("rail",[a("button","max-width: var(--n-button-width-pressed);")])]),a("rail",[j("&:active",[a("button","max-width: var(--n-button-width-pressed);")])]),s("active",[s("pressed",[a("rail",[a("button","left: calc(100% - var(--n-offset) - var(--n-button-width-pressed));")])]),a("rail",[j("&:active",[a("button","left: calc(100% - var(--n-offset) - var(--n-button-width-pressed));")])])])])])]),s("active",[a("rail",[a("button","left: calc(100% - var(--n-button-width) - var(--n-offset))")])]),a("rail",`
 overflow: hidden;
 height: var(--n-rail-height);
 min-width: var(--n-rail-width);
 border-radius: var(--n-rail-border-radius);
 cursor: pointer;
 position: relative;
 transition:
 opacity .3s var(--n-bezier),
 background .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 background-color: var(--n-rail-color);
 `,[a("button-icon",`
 color: var(--n-icon-color);
 transition: color .3s var(--n-bezier);
 font-size: calc(var(--n-button-height) - 4px);
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 display: flex;
 justify-content: center;
 align-items: center;
 line-height: 1;
 `,[Y()]),a("button",`
 align-items: center; 
 top: var(--n-offset);
 left: var(--n-offset);
 height: var(--n-button-height);
 width: var(--n-button-width-pressed);
 max-width: var(--n-button-width);
 border-radius: var(--n-button-border-radius);
 background-color: var(--n-button-color);
 box-shadow: var(--n-button-box-shadow);
 box-sizing: border-box;
 cursor: inherit;
 content: "";
 position: absolute;
 transition:
 background-color .3s var(--n-bezier),
 left .3s var(--n-bezier),
 opacity .3s var(--n-bezier),
 max-width .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 `)]),s("active",[a("rail","background-color: var(--n-rail-color-active);")]),s("loading",[a("rail",`
 cursor: wait;
 `)]),s("disabled",[a("rail",`
 cursor: not-allowed;
 opacity: .5;
 `)])]);const Ve=["aria-checked","tabindex","onClick","onFocus","onBlur","onKeyup","onKeydown"],Fe={...Q.props,size:String,value:{type:[String,Number,Boolean],default:void 0},loading:Boolean,defaultValue:{type:[String,Number,Boolean],default:!1},disabled:{type:Boolean,default:void 0},round:{type:Boolean,default:!0},"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],checkedValue:{type:[String,Number,Boolean],default:!0},uncheckedValue:{type:[String,Number,Boolean],default:!1},railStyle:Function,rubberBand:{type:Boolean,default:!0},spinProps:Object,onChange:[Function,Array]};let F;var Te=me({name:"Switch",props:Fe,slots:Object,setup(e){F===void 0&&(typeof CSS<"u"?typeof CSS.supports<"u"?F=CSS.supports("width","max(1px)"):F=!1:F=!0);const{mergedClsPrefixRef:d,inlineThemeDisabled:f,mergedComponentPropsRef:i}=pe(e),v=Q("Switch","-switch",Re,ze,e,d),g=ye(e,{mergedSize(t){var y,x;if(e.size!==void 0)return e.size;if(t)return t.mergedSize.value;const p=(x=(y=i==null?void 0:i.value)==null?void 0:y.Switch)==null?void 0:x.size;return p||"medium"}}),{mergedSizeRef:$,mergedDisabledRef:w}=g,z=L(e.defaultValue),K=Ce(e,"value"),m=_e(K,z),P=D(()=>m.value===e.checkedValue),o=L(!1),r=L(!1),R=D(()=>{const{railStyle:t}=e;if(t)return t({focused:r.value,checked:P.value})});function T(t){const{"onUpdate:value":p,onChange:y,onUpdateValue:x}=e,{nTriggerFormInput:M,nTriggerFormChange:W}=g;p&&E(p,t),x&&E(x,t),y&&E(y,t),z.value=t,M(),W()}function Z(){const{nTriggerFormFocus:t}=g;t()}function ee(){const{nTriggerFormBlur:t}=g;t()}function te(){e.loading||w.value||(m.value!==e.checkedValue?T(e.checkedValue):T(e.uncheckedValue))}function ae(){r.value=!0,Z()}function oe(){r.value=!1,ee(),o.value=!1}function ie(t){e.loading||w.value||t.key===" "&&(m.value!==e.checkedValue?T(e.checkedValue):T(e.uncheckedValue),o.value=!1)}function ne(t){e.loading||w.value||t.key===" "&&(t.preventDefault(),o.value=!0)}const H=D(()=>{const{value:t}=$,{self:{opacityDisabled:p,railColor:y,railColorActive:x,buttonBoxShadow:M,buttonColor:W,boxShadowFocus:re,loadingColor:le,textColor:se,iconColor:ce,[S("buttonHeight",t)]:u,[S("buttonWidth",t)]:de,[S("buttonWidthPressed",t)]:ue,[S("railHeight",t)]:h,[S("railWidth",t)]:V,[S("railBorderRadius",t)]:he,[S("buttonBorderRadius",t)]:be},common:{cubicBezierEaseInOut:fe}}=v.value;let N,U,O;return F?(N=`calc((${h} - ${u}) / 2)`,U=`max(${h}, ${u})`,O=`max(${V}, calc(${V} + ${u} - ${h}))`):(N=I((c(h)-c(u))/2),U=I(Math.max(c(h),c(u))),O=c(h)>c(u)?V:I(c(V)+c(u)-c(h))),{"--n-bezier":fe,"--n-button-border-radius":be,"--n-button-box-shadow":M,"--n-button-color":W,"--n-button-width":de,"--n-button-width-pressed":ue,"--n-button-height":u,"--n-height":U,"--n-offset":N,"--n-opacity-disabled":p,"--n-rail-border-radius":he,"--n-rail-color":y,"--n-rail-color-active":x,"--n-rail-height":h,"--n-rail-width":V,"--n-width":O,"--n-box-shadow-focus":re,"--n-loading-color":le,"--n-text-color":se,"--n-icon-color":ce}}),B=f?xe("switch",D(()=>$.value[0]),H,e):void 0;return{handleClick:te,handleBlur:oe,handleFocus:ae,handleKeyup:ie,handleKeydown:ne,mergedRailStyle:R,pressed:o,mergedClsPrefix:d,mergedValue:m,checked:P,mergedDisabled:w,cssVars:f?void 0:H,themeClass:B==null?void 0:B.themeClass,onRender:B==null?void 0:B.onRender}},render(){const{mergedClsPrefix:e,mergedDisabled:d,checked:f,mergedRailStyle:i,onRender:v,$slots:g}=this;v==null||v();const{checked:$,unchecked:w,icon:z,"checked-icon":K,"unchecked-icon":m}=g,P=!(A(z)&&A(K)&&A(m));return b(),C("div",{role:"switch","aria-checked":f,class:n([`${e}-switch`,this.themeClass,P&&`${e}-switch--icon`,f&&`${e}-switch--active`,d&&`${e}-switch--disabled`,this.round&&`${e}-switch--round`,this.loading&&`${e}-switch--loading`,this.pressed&&`${e}-switch--pressed`,this.rubberBand&&`${e}-switch--rubber-band`]),tabindex:this.mergedDisabled?void 0:0,style:q(this.cssVars),onClick:this.handleClick,onFocus:this.handleFocus,onBlur:this.handleBlur,onKeyup:this.handleKeyup,onKeydown:this.handleKeydown},[_("div",{class:n(`${e}-switch__rail`),"aria-hidden":"true",style:q(i)},[l(()=>k($,o=>k(w,r=>o||r?(b(),C("div",{key:4,"aria-hidden":!0,class:n(`${e}-switch__children-placeholder`)},[_("div",{class:n(`${e}-switch__rail-placeholder`)},[_("div",{class:n(`${e}-switch__button-placeholder`)},null,2),l(()=>o)],2),_("div",{class:n(`${e}-switch__rail-placeholder`)},[_("div",{class:n(`${e}-switch__button-placeholder`)},null,2),l(()=>r)],2)],2)):null))),_("div",{class:n(`${e}-switch__button`)},[l(()=>k(z,o=>k(K,r=>k(m,R=>(b(),J(Be,null,{default:()=>this.loading?(b(),J(ke,Se({key:"loading",clsPrefix:e,strokeWidth:20},this.spinProps),null,16,["clsPrefix"])):this.checked&&(r||o)?(b(),C("div",{class:n(`${e}-switch__button-icon`),key:r?"checked-icon":"icon"},[l(()=>r||o)],2)):!this.checked&&(R||o)?(b(),C("div",{class:n(`${e}-switch__button-icon`),key:R?"unchecked-icon":"icon"},[l(()=>R||o)],2)):null},1024)))))),l(()=>k($,o=>o&&(b(),C("div",{key:"checked",class:n(`${e}-switch__checked`)},[l(()=>o)],2)))),l(()=>k(w,o=>o&&(b(),C("div",{key:"unchecked",class:n(`${e}-switch__unchecked`)},[l(()=>o)],2))))],2)],6)],46,Ve)}});export{Te as S};
