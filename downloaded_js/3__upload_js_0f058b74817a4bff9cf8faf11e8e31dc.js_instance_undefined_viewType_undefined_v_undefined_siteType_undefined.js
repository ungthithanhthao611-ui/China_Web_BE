$(window).on('load', function() {
new WOW().init();
});

/*
if($(window).width()>998){
    $('header .h_top .m_nav li').hover(function(){
        $(this).children('.sub_nav').stop().slideDown()
        
    },function(){
        $(this).children('.sub_nav').stop().slideUp()
        
    })
}else{
    $('header .h_top .m_nav .nav_icon').on('click',function(){
        if($(this).parent('li').hasClass('on')){
            $(this).parent('li').removeClass('on')
            $(this).siblings('.sub_nav').stop().slideUp()
            $(this).find("svg").css('transform','rotate(0deg)')
          }else{
            $(this).parent('li').addClass('on')
            $(this).parent('li').siblings().removeClass('on')
            $(this).parent('li').siblings().children('.sub_nav').stop().slideUp()
            $(this).siblings(".sub_nav").slideDown()
            $(this).find("svg").css('transform','rotate(180deg)')
            $(this).parent('li').siblings().find("svg").css('transform','rotate(0deg)')
          }
    })
}
*/

$('header .u-menu').on('click',function () {
    $(this).toggleClass('on')
    $('header .h_top .m_nav').slideToggle()
    $('.header_nav').slideToggle()
})
/*
$(window).scroll(function() {
   var scrollTop2 = document.documentElement.scrollTop || document.body.scrollTop;
   if(scrollTop2>10){
        $('header').addClass('on')
   }else{
        $('header').removeClass('on')
   }
})
*/
document.addEventListener("mousemove", function(event){
    var y = event.clientY;
  	if($(".header").hasClass("header_bg")){
    	
    }else{
    	  	if(y <= 90){
                $(".header").stop().slideDown();
                $(".header").addClass("header_bg")  	
            }
    }

});
$(".header").mouseleave(function(e){
	 var top_h = $(document).scrollTop();
  	 console.log(top_h);
  	 if(top_h != 0){
     	$(".header").stop().slideUp();
       	$(".header").removeClass("header_bg");
     }else{
       $(".header").removeClass("header_bg");
       if($('.header').hasClass("header_top")){
       		console.log("??")
       }else{
       		$(".header").stop().slideUp();
     		
       }
       	
     }
  	 
})
/*$(".colum2").mouseleave(function(){
  	 var top_h = document.documentElement.scrollTop || document.body.scrollTop;
  	 if(top_h != 0){
     	$(".header").stop().slideUp();
       	$(".header").removeClass("header_bg");
     }else{
     	$(".header").removeClass("header_bg");
     }
})*/
var _width=$(window).width();
if(_width>1200){
		
		$(".header_nav>div").hover(function(){
			$(this).find(".colum2").stop().slideToggle();
		})
		$(window).scroll(function () {
         
            var scrollTop2 = document.documentElement.scrollTop || document.body.scrollTop;
            if (scrollTop2 > 100) {
                $(".header").stop().slideUp();
              	

            } else {
                /*$(".header").stop().slideDown()*/
                
            }
			
          	if(scrollTop2 != 0){
            		$(".header").removeClass("header_bg");
              		$(".header").removeClass("header_top")
            }else{
            	$(".header").addClass("header_top")
            }

        })
}else{
  $(window).scroll(function () {
         
            var scrollTop2 = document.documentElement.scrollTop || document.body.scrollTop;
            if (scrollTop2 > 100) {
                $(".header").stop().slideUp();
              	

            } else {
                $(".header").stop().slideDown()
                
            }


        })
  	$(".u-menu").click(function(){
      	$(this).toggleClass('on')
    	$(".header_nav").slideToggle();
      	$("body").toggleClass("body_act")
    })
	$(".xuan").click(function(){
    	$(this).toggleClass("xuan_act");
      	$(this).siblings().slideToggle();
      
      	$(this).parent().siblings().find(".xuan").removeClass("xuan_act");
        $(this).parent().siblings().find(".colum2").slideUp();
      	
      	

    })
}
