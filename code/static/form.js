// Copy the last question (does not matter which as we blank out all the data
// anyway), append it to the list of questions
$("#new-question").click(function(event){
    if ($('.question-box').length == 1) {
        $("#delete-question").removeClass('disabled');
    }
    var $question = $("div[class=question-box]:last");
    var $clone = $question.clone(true, true);
    var $num = parseInt($clone.attr('id')) + 1;
    $clone.attr('id', $num);
    // go through all the fields, increment the number for the id and name,
    // and finally clear the value
    $clone.find('input, select').each(function(index){
        // I assert that we use the convention of NAME_num where '_' not used in
        // NAME -- too lazy to do regex
        var $name_chunks = $(this).attr('id').split('_');
        if ($name_chunks.length == 3) {
            // remember that for choices there are 3 parts to join
            $clone.find('label').eq(index).attr('for', `${$name_chunks[0]}_${$num}_${$name_chunks[2]}`);
            $clone.find('input, select').eq(index).attr('id', `${$name_chunks[0]}_${$num}_${$name_chunks[2]}`);
            $clone.find('input, select').eq(index).attr('name', `${$name_chunks[0]}_${$num}_${$name_chunks[2]}`);
        }
        else {
            $clone.find('label').eq(index).attr('for', `${$name_chunks[0]}_${$num}`);
            $clone.find('input, select').eq(index).attr('id', `${$name_chunks[0]}_${$num}`);
            $clone.find('input, select').eq(index).attr('name', `${$name_chunks[0]}_${$num}`);
        }
        $clone.find('input, select').eq(index).val("");
    });
    $clone.find(`#new-choice_${$num - 1}`).attr('id', `#new-choice_${$num}`);
    $clone.find(`#delete-choice_${$num - 1}`).attr('id', `#delete-choice_${$num}`);
    $clone.insertAfter($question);
    return false;
})

// Delete final question (closest to the DELETE button as it is at the end
// of the form
$("#delete-question").click(function(event){
    if ($('.question-box').length >= 2) {
        $("div[class=question-box]:last").remove();
        if ($('.question-box').length == 1) {
            $("#delete-question").addClass('disabled');
        }
    }
    return false;
})

// Append a new choice
$(".new-choice").click(function(event){
    var $question = $(this).parent();
    if ($question.find('.choice-box').length == 2) {
        $question.find('.delete-choice').removeClass('disabled');
    }
    var $choice = $question.find("div[class=choice-box]:last");
    var $clone = $choice.clone(true);
    $clone.find('input').each(function(index){
        // choice name convention: choice_Q_C where Q = question num and C is choice num
        var $name_chunks = $(this).attr('name').split('_');
        $num = (parseInt($name_chunks[2])) + 1;
        $clone.find('label').eq(index).attr('for', `${$name_chunks[0]}_${$name_chunks[1]}_${$num}`);
        $clone.find('input').eq(index).attr('id', `${$name_chunks[0]}_${$name_chunks[1]}_${$num}`);
        $clone.find('input').eq(index).attr('name', `${$name_chunks[0]}_${$name_chunks[1]}_${$num}`);
        $clone.find('input').eq(index).val("");
    });
    // when we add a new choice, we need to update the number of possible maximum
    // answers
    $question.find('select').append($('<option>', {
        value: $num - 1,
        text: $num - 1
    }));
    $clone.insertAfter($choice);
    return false;
});

// Delete last choice
$(".delete-choice").click(function(event){
    var $question = $(this).parent();
    if ($question.find('.choice-box').length >= 3) {
        $question.find("div[class=choice-box]:last").remove();
        if ($question.find('.choice-box').length == 2) {
            $(this).addClass('disabled');
        }
        // remove the highest number choice for max answers
        $question.find('select option:last-child').remove();
    }
    return false;
});