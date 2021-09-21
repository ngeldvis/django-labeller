$( document ).ready(function() {

    var toggleListViewButton = $('#toggle-list-btn');
    toggleListViewButton.click(function() {
        if( $('#img-list').hasClass('hidden')) {
            $('#img-list').removeClass('hidden');
            $('#img-grid').addClass('hidden');
        } else {
            $('#img-grid').removeClass('hidden');
            $('#img-list').addClass('hidden');
        }
    })

});
