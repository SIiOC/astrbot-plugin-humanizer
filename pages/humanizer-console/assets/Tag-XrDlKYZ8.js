import{G as go,cn as Co,b2 as r,J as bo,a6 as v,a7 as p,a8 as P,H as S,d as uo,K as G,U as K,o as y,c as B,V as m,a as vo,L as x,g as fo,a4 as ko,n as L,M as po,Q as mo,ad as xo,h as yo,R as zo,e as O,ag as i,ah as Io,co as A,al as Po,$ as So,a0 as Bo}from"./index-k2JXiZDX.js";function $o(o){const{textColor2:g,primaryColorHover:b,primaryColorPressed:f,primaryColor:a,infoColor:n,successColor:c,warningColor:s,errorColor:t,baseColor:d,borderColor:k,opacityDisabled:$,tagColor:H,closeIconColor:z,closeIconColorHover:u,closeIconColorPressed:e,borderRadiusSmall:l,fontSizeMini:C,fontSizeTiny:h,fontSizeSmall:M,fontSizeMedium:_,heightMini:R,heightTiny:T,heightSmall:E,heightMedium:W,closeColorHover:w,closeColorPressed:F,buttonColor2Hover:U,buttonColor2Pressed:V,fontWeightStrong:N}=o;return{...Co,closeBorderRadius:l,heightTiny:R,heightSmall:T,heightMedium:E,heightLarge:W,borderRadius:l,opacityDisabled:$,fontSizeTiny:C,fontSizeSmall:h,fontSizeMedium:M,fontSizeLarge:_,fontWeightStrong:N,textColorCheckable:g,textColorHoverCheckable:g,textColorPressedCheckable:g,textColorChecked:d,colorCheckable:"#0000",colorHoverCheckable:U,colorPressedCheckable:V,colorChecked:a,colorCheckedHover:b,colorCheckedPressed:f,border:`1px solid ${k}`,textColor:g,color:H,colorBordered:"rgb(250, 250, 252)",closeIconColor:z,closeIconColorHover:u,closeIconColorPressed:e,closeColorHover:w,closeColorPressed:F,borderPrimary:`1px solid ${r(a,{alpha:.3})}`,textColorPrimary:a,colorPrimary:r(a,{alpha:.12}),colorBorderedPrimary:r(a,{alpha:.1}),closeIconColorPrimary:a,closeIconColorHoverPrimary:a,closeIconColorPressedPrimary:a,closeColorHoverPrimary:r(a,{alpha:.12}),closeColorPressedPrimary:r(a,{alpha:.18}),borderInfo:`1px solid ${r(n,{alpha:.3})}`,textColorInfo:n,colorInfo:r(n,{alpha:.12}),colorBorderedInfo:r(n,{alpha:.1}),closeIconColorInfo:n,closeIconColorHoverInfo:n,closeIconColorPressedInfo:n,closeColorHoverInfo:r(n,{alpha:.12}),closeColorPressedInfo:r(n,{alpha:.18}),borderSuccess:`1px solid ${r(c,{alpha:.3})}`,textColorSuccess:c,colorSuccess:r(c,{alpha:.12}),colorBorderedSuccess:r(c,{alpha:.1}),closeIconColorSuccess:c,closeIconColorHoverSuccess:c,closeIconColorPressedSuccess:c,closeColorHoverSuccess:r(c,{alpha:.12}),closeColorPressedSuccess:r(c,{alpha:.18}),borderWarning:`1px solid ${r(s,{alpha:.35})}`,textColorWarning:s,colorWarning:r(s,{alpha:.15}),colorBorderedWarning:r(s,{alpha:.12}),closeIconColorWarning:s,closeIconColorHoverWarning:s,closeIconColorPressedWarning:s,closeColorHoverWarning:r(s,{alpha:.12}),closeColorPressedWarning:r(s,{alpha:.18}),borderError:`1px solid ${r(t,{alpha:.23})}`,textColorError:t,colorError:r(t,{alpha:.1}),colorBorderedError:r(t,{alpha:.08}),closeIconColorError:t,closeIconColorHoverError:t,closeIconColorPressedError:t,closeColorHoverError:r(t,{alpha:.12}),closeColorPressedError:r(t,{alpha:.18})}}const Ho={common:go,self:$o};var Mo={color:Object,type:{type:String,default:"default"},round:Boolean,size:String,closable:Boolean,disabled:{type:Boolean,default:void 0}},_o=bo("tag",`
 --n-close-margin: var(--n-close-margin-top) var(--n-close-margin-right) var(--n-close-margin-bottom) var(--n-close-margin-left);
 white-space: nowrap;
 position: relative;
 box-sizing: border-box;
 cursor: default;
 display: inline-flex;
 align-items: center;
 flex-wrap: nowrap;
 padding: var(--n-padding);
 border-radius: var(--n-border-radius);
 color: var(--n-text-color);
 background-color: var(--n-color);
 transition: 
 border-color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 line-height: 1;
 height: var(--n-height);
 font-size: var(--n-font-size);
`,[v("strong",`
 font-weight: var(--n-font-weight-strong);
 `),p("border",`
 pointer-events: none;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 border-radius: inherit;
 border: var(--n-border);
 transition: border-color .3s var(--n-bezier);
 `),p("icon",`
 display: flex;
 margin: 0 4px 0 0;
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 font-size: var(--n-avatar-size-override);
 `),p("avatar",`
 display: flex;
 margin: 0 6px 0 0;
 `),p("close",`
 margin: var(--n-close-margin);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `),v("round",`
 padding: 0 calc(var(--n-height) / 3);
 border-radius: calc(var(--n-height) / 2);
 `,[p("icon",`
 margin: 0 4px 0 calc((var(--n-height) - 8px) / -2);
 `),p("avatar",`
 margin: 0 6px 0 calc((var(--n-height) - 8px) / -2);
 `),v("closable",`
 padding: 0 calc(var(--n-height) / 4) 0 calc(var(--n-height) / 3);
 `)]),v("icon, avatar",[v("round",`
 padding: 0 calc(var(--n-height) / 3) 0 calc(var(--n-height) / 2);
 `)]),v("disabled",`
 cursor: not-allowed !important;
 opacity: var(--n-opacity-disabled);
 `),v("checkable",`
 cursor: pointer;
 box-shadow: none;
 color: var(--n-text-color-checkable);
 background-color: var(--n-color-checkable);
 `,[P("disabled",[S("&:hover","background-color: var(--n-color-hover-checkable);",[P("checked","color: var(--n-text-color-hover-checkable);")]),S("&:active","background-color: var(--n-color-pressed-checkable);",[P("checked","color: var(--n-text-color-pressed-checkable);")])]),v("checked",`
 color: var(--n-text-color-checked);
 background-color: var(--n-color-checked);
 `,[P("disabled",[S("&:hover","background-color: var(--n-color-checked-hover);"),S("&:active","background-color: var(--n-color-checked-pressed);")])])])]);const Ro=["onClick","onMouseenter","onMouseleave"],To={...G.props,...Mo,bordered:{type:Boolean,default:void 0},checked:Boolean,checkable:Boolean,strong:Boolean,triggerClickOnClose:Boolean,onClose:[Array,Function],onMouseenter:Function,onMouseleave:Function,"onUpdate:checked":Function,onUpdateChecked:Function,internalCloseFocusable:{type:Boolean,default:!0},internalCloseIsButtonTag:{type:Boolean,default:!0},onCheckedChange:Function},Eo=Bo("n-tag");var wo=uo({name:"Tag",props:To,slots:Object,setup(o){const g=yo(null),{mergedBorderedRef:b,mergedClsPrefixRef:f,inlineThemeDisabled:a,mergedRtlRef:n,mergedComponentPropsRef:c}=po(o),s=O(()=>{var e,l;return o.size||((l=(e=c==null?void 0:c.value)==null?void 0:e.Tag)==null?void 0:l.size)||"medium"}),t=G("Tag","-tag",_o,Ho,o,f);Po(Eo,{roundRef:So(o,"round")});function d(){if(!o.disabled&&o.checkable){const{checked:e,onCheckedChange:l,onUpdateChecked:C,"onUpdate:checked":h}=o;C&&C(!e),h&&h(!e),l&&l(!e)}}function k(e){if(o.triggerClickOnClose||e.stopPropagation(),!o.disabled){const{onClose:l}=o;l&&zo(l,e)}}const $={setTextContent(e){const{value:l}=g;l&&(l.textContent=e)}},H=mo("Tag",n,f),z=O(()=>{const{type:e,color:{color:l,textColor:C}={}}=o,h=s.value,{common:{cubicBezierEaseInOut:M},self:{padding:_,closeMargin:R,borderRadius:T,opacityDisabled:E,textColorCheckable:W,textColorHoverCheckable:w,textColorPressedCheckable:F,textColorChecked:U,colorCheckable:V,colorHoverCheckable:N,colorPressedCheckable:J,colorChecked:Q,colorCheckedHover:q,colorCheckedPressed:X,closeBorderRadius:Y,fontWeightStrong:Z,[i("colorBordered",e)]:oo,[i("closeSize",h)]:eo,[i("closeIconSize",h)]:ro,[i("fontSize",h)]:lo,[i("height",h)]:j,[i("color",e)]:ao,[i("textColor",e)]:co,[i("border",e)]:no,[i("closeIconColor",e)]:D,[i("closeIconColorHover",e)]:so,[i("closeIconColorPressed",e)]:to,[i("closeColorHover",e)]:io,[i("closeColorPressed",e)]:ho}}=t.value,I=Io(R);return{"--n-font-weight-strong":Z,"--n-avatar-size-override":`calc(${j} - 8px)`,"--n-bezier":M,"--n-border-radius":T,"--n-border":no,"--n-close-icon-size":ro,"--n-close-color-pressed":ho,"--n-close-color-hover":io,"--n-close-border-radius":Y,"--n-close-icon-color":D,"--n-close-icon-color-hover":so,"--n-close-icon-color-pressed":to,"--n-close-icon-color-disabled":D,"--n-close-margin-top":I.top,"--n-close-margin-right":I.right,"--n-close-margin-bottom":I.bottom,"--n-close-margin-left":I.left,"--n-close-size":eo,"--n-color":l||(b.value?oo:ao),"--n-color-checkable":V,"--n-color-checked":Q,"--n-color-checked-hover":q,"--n-color-checked-pressed":X,"--n-color-hover-checkable":N,"--n-color-pressed-checkable":J,"--n-font-size":lo,"--n-height":j,"--n-opacity-disabled":E,"--n-padding":_,"--n-text-color":C||co,"--n-text-color-checkable":W,"--n-text-color-checked":U,"--n-text-color-hover-checkable":w,"--n-text-color-pressed-checkable":F}}),u=a?xo("tag",O(()=>{let e="";const{type:l,color:{color:C,textColor:h}={}}=o;return e+=l[0],e+=s.value[0],C&&(e+=`a${A(C)}`),h&&(e+=`b${A(h)}`),b.value&&(e+="c"),e}),z,o):void 0;return{...$,rtlEnabled:H,mergedClsPrefix:f,contentRef:g,mergedBordered:b,handleClick:d,handleCloseClick:k,cssVars:a?void 0:z,themeClass:u==null?void 0:u.themeClass,onRender:u==null?void 0:u.onRender}},render(){const{mergedClsPrefix:o,rtlEnabled:g,closable:b,color:{borderColor:f}={},round:a,onRender:n,$slots:c}=this;n==null||n();const s=K(c.avatar,d=>d&&(y(),B("div",{class:x(`${o}-tag__avatar`)},[m(()=>d)],2))),t=K(c.icon,d=>d&&(y(),B("div",{class:x(`${o}-tag__icon`)},[m(()=>d)],2)));return y(),B("div",{class:x([`${o}-tag`,this.themeClass,{[`${o}-tag--rtl`]:g,[`${o}-tag--strong`]:this.strong,[`${o}-tag--disabled`]:this.disabled,[`${o}-tag--checkable`]:this.checkable,[`${o}-tag--checked`]:this.checkable&&this.checked,[`${o}-tag--round`]:a,[`${o}-tag--avatar`]:s,[`${o}-tag--icon`]:t,[`${o}-tag--closable`]:b}]),style:L(this.cssVars),onClick:this.handleClick,onMouseenter:this.onMouseenter,onMouseleave:this.onMouseleave},[m(()=>t||s),vo("span",{class:x(`${o}-tag__content`),ref:"contentRef"},[m(()=>{var d,k;return(k=(d=this.$slots).default)==null?void 0:k.call(d)})],2),!this.checkable&&b?(y(),fo(ko,{key:0,clsPrefix:o,class:x(`${o}-tag__close`),disabled:this.disabled,onClick:this.handleCloseClick,focusable:this.internalCloseFocusable,round:a,isButtonTag:this.internalCloseIsButtonTag,absolute:!0},null,8,["clsPrefix","class","disabled","onClick","focusable","round","isButtonTag"])):m(()=>null),!this.checkable&&this.mergedBordered?(y(),B("div",{key:2,class:x(`${o}-tag__border`),style:L({borderColor:f})},null,6)):m(()=>null)],46,Ro)}});export{wo as T};
