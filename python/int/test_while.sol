class Main : Object {
  run [ |
    i := 1.
    _ := [ | b := i greaterThan: 5. r := b not. ] whileTrue: [ |
      s := i asString.
      _ := s print.
      i := i plus: 1.
    ].
  ]
}
