// Copy the last question (does not matter which as we blank out all the data
// anyway), append it to the list of questions
$("#new-question").click(function(event){
    if ($('.question-box').length == 1) {
        $("#delete-question").disabled = false;
    }
    var $question = $("div[class=question-box]:last");
    var $clone = $question.clone();
    // go through all the fields, increment the number for the id and name,
    // and finally clear the value
    $clone.find('input').each(function(index){
        // I assert that we use the convention of NAME_num where '_' not used in
        // NAME -- too lazy to do regex
        var $name_chunks = $(this).attr('name').split('_');
        $num = (parseInt($name_chunks[1])) + 1;
        $clone.find('label').eq(index).attr('for', $name_chunks[0] + $num);
        $clone.find('input').eq(index).attr('id', $name_chunks[0] + $num);
        $clone.find('input').eq(index).attr('name', $name_chunks[0] + $num);
        $clone.find('input').eq(index).attr('value', "");
    });
    $clone.insertAfter($question);
    return false;
})

// Delete final question (closest to the DELETE button as it is at the end
// of the form
$("#delete-question").click(function(event){
    if ($('.question-box').length >= 2) {
        $("#delete-question").disabled = false;
        $("div[class=question-box]:last").remove();
    }
    else {
        $("#delete-question").disabled = true;
    }
    return false;
})