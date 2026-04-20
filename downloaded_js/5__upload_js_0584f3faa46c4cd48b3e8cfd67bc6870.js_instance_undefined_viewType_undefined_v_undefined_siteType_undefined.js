
    $(".nav_search").click(function(){
        $(".search_mask").fadeIn();
    }) 
    $(".mask_close").click(function(){
        $(".search_mask").fadeOut();
    }) 
    $(".mask_btn").click(function(){
        var txt=$(this).siblings().val().trim();
        /*location.href='/globalSearch.html?keywords='+txt +'&appIds=all'*/
        window.open('/globalSearch.html?keywords='+txt +'&appIds=all');
        $(this).siblings().val('');
    })
    document.addEventListener("keydown", function(event) {
      if (event.key === "Enter" && $(".search_mask").css("display") == 'block') {
        // ?????????
       var text=$('.mask_input').val().trim();
        window.open('/globalSearch.html?keywords='+text +'&appIds=all');
        $('.mask_input').siblings().val('');
      }
    });
